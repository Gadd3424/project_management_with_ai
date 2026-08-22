from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from ..audit import add_audit
from ..dependencies import Csrf, CurrentUser, DbSession, Tenant
from ..models import ModelArtifact, ModelExperiment
from ..schemas import ExperimentCreate, ExperimentRead

router = APIRouter(tags=["model-registry"])


@router.get("/model-experiments", response_model=list[ExperimentRead])
async def list_experiments(db: DbSession, tenant: Tenant) -> list[ModelExperiment]:
    return list(
        (
            await db.scalars(
                select(ModelExperiment)
                .where(ModelExperiment.organization_id == tenant.organization_id)
                .order_by(ModelExperiment.created_at.desc())
            )
        ).all()
    )


@router.post("/model-experiments", response_model=ExperimentRead, status_code=202)
async def create_experiment(
    payload: ExperimentCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> ModelExperiment:
    experiment = ModelExperiment(
        organization_id=tenant.organization_id,
        name=payload.name,
        configuration={
            "adapter_paths": payload.adapter_paths,
            "population_size": payload.population_size,
            "generations": payload.generations,
        },
        random_seed=payload.random_seed,
        created_by=user.id,
    )
    db.add(experiment)
    await db.flush()
    add_audit(db, request, tenant.organization_id, user, "experiment.create", "model_experiment", experiment.id)
    await db.commit()
    await db.refresh(experiment)
    try:
        from apps.worker.tasks import run_evolution_experiment

        run_evolution_experiment.delay(experiment.id)
    except Exception:
        # API remains usable without a local broker; the worker can resume queued experiments later.
        pass
    return experiment


@router.get("/model-experiments/{experiment_id}", response_model=ExperimentRead)
async def get_experiment(experiment_id: str, db: DbSession, tenant: Tenant) -> ModelExperiment:
    experiment = await db.scalar(
        select(ModelExperiment).where(
            ModelExperiment.id == experiment_id,
            ModelExperiment.organization_id == tenant.organization_id,
        )
    )
    if not experiment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return experiment


@router.post("/model-experiments/{experiment_id}/cancel", response_model=ExperimentRead)
async def cancel_experiment(experiment_id: str, db: DbSession, tenant: Tenant, _: Csrf) -> ModelExperiment:
    experiment = await get_experiment(experiment_id, db, tenant)
    if experiment.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Experiment is already terminal")
    experiment.cancel_requested = True
    await db.commit()
    await db.refresh(experiment)
    return experiment


@router.get("/models")
async def list_models(db: DbSession, tenant: Tenant) -> list[dict]:
    models = (
        await db.scalars(
            select(ModelArtifact).where(
                (ModelArtifact.organization_id == tenant.organization_id) | (ModelArtifact.organization_id.is_(None))
            )
        )
    ).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "version": item.model_version,
            "base_model_id": item.base_model_id,
            "parent_model_ids": item.parent_model_ids,
            "metrics": item.metrics,
            "approval_status": item.approval_status,
            "deployment_status": item.deployment_status,
        }
        for item in models
    ]


@router.post("/models/{model_id}/approve")
async def approve_model(
    model_id: str, request: Request, db: DbSession, user: CurrentUser, tenant: Tenant, _: Csrf
) -> dict[str, str]:
    item = await db.get(ModelArtifact, model_id)
    if not item or item.organization_id not in {None, tenant.organization_id}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    if tenant.role not in {"owner", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    item.approval_status = "approved"
    add_audit(db, request, tenant.organization_id, user, "model.approve", "model", model_id)
    await db.commit()
    return {"id": item.id, "approval_status": item.approval_status}


@router.post("/models/{model_id}/deploy")
async def deploy_model(
    model_id: str, request: Request, db: DbSession, user: CurrentUser, tenant: Tenant, _: Csrf
) -> dict[str, str]:
    item = await db.get(ModelArtifact, model_id)
    if not item or item.organization_id not in {None, tenant.organization_id}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    if tenant.role not in {"owner", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    if item.approval_status != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Model requires human approval")
    item.deployment_status = "shadow"
    add_audit(db, request, tenant.organization_id, user, "model.deploy_shadow", "model", model_id)
    await db.commit()
    return {"id": item.id, "deployment_status": item.deployment_status}
