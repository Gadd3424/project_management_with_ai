from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from celery import shared_task
from sqlalchemy import select

from apps.api.app.config import get_settings
from apps.api.app.db import SessionLocal
from apps.api.app.models import ModelArtifact, ModelCandidate, ModelExperiment, OutboxEvent
from apps.api.app.services.invitation_service import invitation_token
from apps.api.app.services.user_management_service import UserManagementService
from services.evolutionary_merge import EvolutionConfig, GeneticOptimizer

logger = logging.getLogger(__name__)


def demo_fitness(weights: list[float]) -> tuple[float, dict[str, float]]:
    target = [0.55, 0.3, 0.15][: len(weights)]
    if len(weights) > len(target):
        target.extend([0.0] * (len(weights) - len(target)))
    total = sum(target)
    target = [value / total for value in target]
    quality = 1.0 - sum(abs(a - b) for a, b in zip(weights, target, strict=True)) / 2
    calibration = 1.0 - abs(weights[0] - target[0])
    latency_penalty = 0.02 * sum(1 for weight in weights if weight > 0.1)
    fitness = 0.65 * quality + 0.35 * calibration - latency_penalty
    return fitness, {
        "suggestion_quality": quality,
        "calibration": calibration,
        "latency_penalty": latency_penalty,
    }


async def cancel_requested(experiment_id: str) -> bool:
    async with SessionLocal() as db:
        value = await db.scalar(select(ModelExperiment.cancel_requested).where(ModelExperiment.id == experiment_id))
        return bool(value)


async def execute_experiment(experiment_id: str) -> dict:
    async with SessionLocal() as db:
        experiment = await db.get(ModelExperiment, experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} does not exist")
        experiment.status = "running"
        await db.commit()
        config_data = experiment.configuration

    artifact_dir = Path("artifacts") / "experiments" / experiment_id
    checkpoint = artifact_dir / "checkpoint.json"
    optimizer = GeneticOptimizer(
        EvolutionConfig(
            gene_count=len(config_data["adapter_paths"]),
            population_size=int(config_data["population_size"]),
            generations=int(config_data["generations"]),
            random_seed=experiment.random_seed,
        )
    )
    cancelled = False

    def should_cancel() -> bool:
        nonlocal cancelled
        cancelled = asyncio.run(cancel_requested(experiment_id))
        return cancelled

    try:
        result = optimizer.run(demo_fitness, checkpoint, should_cancel)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        best_path = artifact_dir / "best-genome.json"
        best_payload = {
            "weights": result.best.weights,
            "fitness": result.best.fitness,
            "metrics": result.best.metrics,
            "history": result.history,
        }
        best_path.write_text(json.dumps(best_payload, indent=2), encoding="utf-8")
        checksum = hashlib.sha256(best_path.read_bytes()).hexdigest()
        async with SessionLocal() as db:
            experiment = await db.get(ModelExperiment, experiment_id)
            if not experiment:
                raise ValueError("Experiment disappeared")
            experiment.status = "cancelled" if cancelled else "completed"
            experiment.progress = result.completed_generations / int(config_data["generations"])
            experiment.checkpoint_path = str(checkpoint)
            candidate = ModelCandidate(
                organization_id=experiment.organization_id,
                experiment_id=experiment.id,
                genome={"weights": result.best.weights},
                generation=result.completed_generations - 1,
                fitness=result.best.fitness,
                individual_metrics=result.best.metrics,
                artifact_path=str(best_path),
                status="evaluated",
            )
            db.add(candidate)
            if not cancelled:
                db.add(
                    ModelArtifact(
                        organization_id=experiment.organization_id,
                        name=f"{experiment.name} best candidate",
                        model_version=f"ga-{experiment.id[:8]}",
                        base_model_id="demo/base-model",
                        parent_model_ids=config_data["adapter_paths"],
                        artifact_path=str(best_path),
                        checksum=checksum,
                        metrics=result.best.metrics,
                        created_by=experiment.created_by,
                    )
                )
            await db.commit()
        return best_payload
    except Exception:
        async with SessionLocal() as db:
            experiment = await db.get(ModelExperiment, experiment_id)
            if experiment:
                experiment.status = "failed"
                await db.commit()
        raise


@shared_task(name="run_evolution_experiment")
def run_evolution_experiment(experiment_id: str) -> dict:
    return asyncio.run(execute_experiment(experiment_id))


async def deliver_outbox_events() -> int:
    delivered = 0
    async with SessionLocal() as db:
        events = (
            await db.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "pending",
                    OutboxEvent.available_at <= datetime.now(UTC),
                )
                .order_by(OutboxEvent.created_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for event in events:
            event.attempt_count += 1
            if event.event_type.startswith("user.invitation."):
                if get_settings().app_env != "development":
                    # Production delivery intentionally requires an explicitly configured provider.
                    continue
                invite_id = str(event.payload["invitation_id"])
                logger.warning(
                    "DEV MAILBOX invitation recipient=%s url=http://localhost:3000/invitations/accept?token=%s",
                    event.payload["email"],
                    invitation_token(invite_id),
                )
            elif event.event_type == "user.password_reset.requested":
                logger.warning("DEV MAILBOX password reset requested recipient=%s", event.payload["email"])
            elif event.event_type == "user.direct_registration.created":
                if get_settings().app_env != "development":
                    continue
                logger.warning(
                    "DEV MAILBOX direct registration recipient=%s temporary_password=%s",
                    event.payload["email"],
                    UserManagementService.temporary_password(str(event.payload["user_id"])),
                )
            event.status = "processed"
            event.processed_at = datetime.now(UTC)
            delivered += 1
        await db.commit()
    return delivered


@shared_task(name="process_outbox_events")
def process_outbox_events() -> int:
    return asyncio.run(deliver_outbox_events())
