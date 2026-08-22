import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

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
