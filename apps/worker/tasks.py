from __future__ import annotations

import asyncio
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
from services.evolutionary_merge.lora_merge import load_metadata, merge_adapters

logger = logging.getLogger(__name__)


def project_proposal_fitness(adapter_paths: list[Path]):
    """Build a reproducible fitness function from versioned offline evaluation sidecars."""
    evaluations: list[dict[str, float]] = []
    for path in adapter_paths:
        evaluation_path = path.with_suffix(".evaluation.json")
        if not evaluation_path.exists():
            raise ValueError(f"Missing offline evaluation: {evaluation_path}")
        payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
        evaluations.append({key: float(value) for key, value in payload["metrics"].items()})
    required = {"schema_validity", "relevance", "groundedness", "safety", "latency_score"}
    if any(not required <= item.keys() for item in evaluations):
        raise ValueError(f"Evaluation metrics must include {sorted(required)}")

    def evaluate(weights: list[float]) -> tuple[float, dict[str, float]]:
        metrics = {
            key: sum(weight * item[key] for weight, item in zip(weights, evaluations, strict=True)) for key in required
        }
        fitness = (
            0.25 * metrics["schema_validity"]
            + 0.25 * metrics["relevance"]
            + 0.2 * metrics["groundedness"]
            + 0.2 * metrics["safety"]
            + 0.1 * metrics["latency_score"]
        )
        return fitness, metrics

    return evaluate


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
    adapter_paths = [Path(value) for value in config_data["adapter_paths"]]
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
        result = optimizer.run(project_proposal_fitness(adapter_paths), checkpoint, should_cancel)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        best_path = artifact_dir / "merged-adapter.safetensors"
        checksum = merge_adapters(adapter_paths, result.best.weights, best_path)
        metadata = load_metadata(adapter_paths[0])
        best_path.with_suffix(".json").write_text(
            json.dumps(
                {
                    "base_model_id": metadata.base_model_id,
                    "revision": metadata.revision,
                    "rank": metadata.rank,
                    "target_modules": list(metadata.target_modules),
                    "parent_model_ids": config_data["adapter_paths"],
                    "weights": result.best.weights,
                    "evaluation_dataset_version": config_data["evaluation_dataset_version"],
                    "prompt_version": config_data["prompt_version"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        best_payload = {
            "weights": result.best.weights,
            "fitness": result.best.fitness,
            "metrics": result.best.metrics,
            "history": result.history,
        }
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
                parent_model_ids=config_data["adapter_paths"],
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
                        base_model_id=metadata.base_model_id,
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

