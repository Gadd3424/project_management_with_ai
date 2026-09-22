import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel, Field
from safetensors import safe_open

from services.evolutionary_merge.lora_merge import verify_checksum

app = FastAPI(title="Project AI Inference", version="0.1.0")


class PredictionRequest(BaseModel):
    task_id: str
    features: dict[str, Any]
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class PredictionResponse(BaseModel):
    delay_probability: float | None
    confidence: float
    explanation: str
    data_sufficient: bool
    model_id: str
    model_version: str
    inference_ms: int


class EvolutionModel(BaseModel):
    id: str
    version: str
    artifact_path: str
    checksum: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class ProjectDefaultsRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    model: EvolutionModel


class ProjectChangeRequest(BaseModel):
    snapshot: dict[str, Any]
    model: EvolutionModel


class ProjectTaskSuggestionsRequest(BaseModel):
    snapshot: dict[str, Any]
    model: EvolutionModel


class ProjectProposalResponse(BaseModel):
    proposed_values: dict[str, Any]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence: list[dict[str, Any]]
    assumptions: list[str]
    risks: list[str]
    expected_effect: str
    provider: str
    model_id: str
    model_version: str
    inference_ms: int


def model_signal(model: EvolutionModel) -> float:
    """Read the approved merged Safetensors artifact and derive a bounded adaptation signal."""
    path = Path(model.artifact_path)
    if path.suffix != ".safetensors" or not path.is_file():
        raise ValueError("Evolutionary model artifact is unavailable")
    verify_checksum(path, model.checksum)
    values: list[float] = []
    with safe_open(path, framework="np") as handle:
        for key in list(handle.keys())[:16]:
            tensor = handle.get_tensor(key).astype(np.float64)
            if not np.isfinite(tensor).all():
                raise ValueError("Evolutionary model contains non-finite tensors")
            values.append(float(np.mean(np.abs(tensor))))
    if not values:
        raise ValueError("Evolutionary model contains no tensors")
    return float(np.tanh(np.mean(values)))


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "provider": "mock"}


@app.post("/v1/predict/delay", response_model=PredictionResponse)
def predict_delay(payload: PredictionRequest) -> PredictionResponse:
    started = time.perf_counter()
    days = payload.features.get("days_to_due")
    has_description = bool(payload.features.get("description_length", 0))
    sufficient = days is not None or has_description
    score = 0.2
    if days is not None:
        score += 0.5 if days < 0 else 0.3 if days <= 2 else 0.1
    if not payload.features.get("has_assignee"):
        score += 0.1
    score = round(min(score, 0.95), 2)
    return PredictionResponse(
        delay_probability=score if sufficient else None,
        confidence=score if sufficient else 0.2,
        explanation=(
            "期限、進捗状態、担当者設定を使用した構造化予測です。"
            if sufficient
            else "予測に必要な期限または説明が不足しています。"
        ),
        data_sufficient=sufficient,
        model_id="mock-delay-model",
        model_version="0.1.0",
        inference_ms=round((time.perf_counter() - started) * 1000),
    )


@app.post("/v1/projects/defaults", response_model=ProjectProposalResponse)
def project_defaults(payload: ProjectDefaultsRequest) -> ProjectProposalResponse:
    from apps.api.app.project_ai_service import mock_defaults

    started = time.perf_counter()
    signal = model_signal(payload.model)
    result = mock_defaults(payload.name)
    proposed = result["proposed_values"]
    proposed["due_date"] = (date.fromisoformat(proposed["due_date"]) + timedelta(days=round(signal * 21))).isoformat()
    result["confidence"] = min(0.95, result["confidence"] + signal * 0.15)
    result["evidence"].append({"type": "evolutionary_model_signal", "value": round(signal, 4)})
    return ProjectProposalResponse(
        **{
            key: value
            for key, value in result.items()
            if key not in {"provider", "model_id", "model_version", "inference_ms"}
        },
        provider="evolutionary_merge",
        model_id=payload.model.id,
        model_version=payload.model.version,
        inference_ms=round((time.perf_counter() - started) * 1000),
    )


@app.post("/v1/projects/change-proposal", response_model=ProjectProposalResponse)
def project_change(payload: ProjectChangeRequest) -> ProjectProposalResponse:
    from apps.api.app.project_ai_service import mock_change_proposal

    started = time.perf_counter()
    signal = model_signal(payload.model)
    result = mock_change_proposal(payload.snapshot)
    result["confidence"] = min(0.95, result["confidence"] + signal * 0.15)
    result["evidence"].append({"type": "evolutionary_model_signal", "value": round(signal, 4)})
    return ProjectProposalResponse(
        **{
            key: value
            for key, value in result.items()
            if key not in {"provider", "model_id", "model_version", "inference_ms"}
        },
        provider="evolutionary_merge",
        model_id=payload.model.id,
        model_version=payload.model.version,
        inference_ms=round((time.perf_counter() - started) * 1000),
    )


@app.post("/v1/projects/task-suggestions", response_model=ProjectProposalResponse)
def project_task_suggestions(payload: ProjectTaskSuggestionsRequest) -> ProjectProposalResponse:
    from apps.api.app.project_ai_service import mock_task_suggestions

    started = time.perf_counter()
    signal = model_signal(payload.model)
    result = mock_task_suggestions(payload.snapshot)
    tasks = result["proposed_values"]["tasks"]
    for task in tasks:
        task["confidence"] = min(0.98, task["confidence"] + signal * 0.12)
    result["confidence"] = min(0.97, result["confidence"] + signal * 0.15)
    result["evidence"].append({"type": "evolutionary_model_signal", "value": round(signal, 4)})
    return ProjectProposalResponse(
        **{
            key: value
            for key, value in result.items()
            if key not in {"provider", "model_id", "model_version", "inference_ms"}
        },
        provider="evolutionary_merge",
        model_id=payload.model.id,
        model_version=payload.model.version,
        inference_ms=round((time.perf_counter() - started) * 1000),
    )
