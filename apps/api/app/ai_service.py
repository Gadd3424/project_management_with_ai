import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AISuggestion, FeatureSnapshot, Task


def task_features(task: Task, comment_count: int = 0) -> dict[str, Any]:
    now = datetime.now(UTC)
    days_to_due = None
    if task.due_at:
        due = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)
        days_to_due = round((due - now).total_seconds() / 86400, 2)
    return {
        "days_to_due": days_to_due,
        "priority": task.priority,
        "status": task.status,
        "description_length": len(task.description),
        "comment_count": comment_count,
        "has_assignee": bool(task.assignee_id),
    }


def delay_probability(features: dict[str, Any]) -> float:
    score = 0.18
    days = features["days_to_due"]
    if days is not None:
        score += 0.45 if days < 0 else 0.3 if days <= 2 else 0.1 if days <= 7 else 0
    if features["status"] == "todo":
        score += 0.12
    if not features["has_assignee"]:
        score += 0.12
    if features["priority"] in {"high", "urgent"}:
        score += 0.06
    return round(min(max(score, 0.05), 0.95), 2)


async def find_references(db: AsyncSession, task: Task) -> list[dict[str, Any]]:
    words = [word for word in task.title.replace("　", " ").split() if len(word) >= 2][:3]
    if not words:
        return []
    predicates = [Task.title.ilike(f"%{word}%") for word in words]
    matches = (
        await db.scalars(
            select(Task)
            .where(
                Task.organization_id == task.organization_id,
                Task.id != task.id,
                Task.deleted_at.is_(None),
                or_(*predicates),
            )
            .limit(3)
        )
    ).all()
    return [{"type": "task", "id": item.id, "title": item.title, "project_id": item.project_id} for item in matches]


async def generate_suggestions(db: AsyncSession, task: Task) -> list[AISuggestion]:
    started = time.perf_counter()
    features = task_features(task)
    snapshot = FeatureSnapshot(
        organization_id=task.organization_id,
        task_id=task.id,
        features=features,
    )
    db.add(snapshot)
    await db.flush()
    references = await find_references(db, task)
    probability = delay_probability(features)
    data_sufficient = features["days_to_due"] is not None or bool(task.description)
    delay = AISuggestion(
        organization_id=task.organization_id,
        project_id=task.project_id,
        task_id=task.id,
        feature_snapshot_id=snapshot.id,
        suggestion_type="delay_risk",
        content={"delay_probability": probability if data_sufficient else None, "data_sufficient": data_sufficient},
        confidence=probability if data_sufficient else 0.2,
        rationale=(
            f"期限までの日数、状態、優先度、担当者設定から遅延確率を{probability:.0%}と推定しました。"
            if data_sufficient
            else "期限または説明が不足しているため、信頼できる遅延予測を作成できません。"
        ),
        features_used=features,
        references=references,
        expected_effect="早期にリスクを確認し、期限または担当計画を見直せます。",
        risks=["デモ用ルールモデルのため、実運用データで再学習する必要があります。"],
        inference_ms=round((time.perf_counter() - started) * 1000),
    )
    action_text = "担当者を決め、完了条件を確認する"
    if task.assignee_id and features["days_to_due"] is not None and features["days_to_due"] <= 3:
        action_text = "担当者と期限内に完了可能か確認し、必要なら作業を分割する"
    elif task.assignee_id:
        action_text = "最初の作業項目と完了条件を確認する"
    action = AISuggestion(
        organization_id=task.organization_id,
        project_id=task.project_id,
        task_id=task.id,
        feature_snapshot_id=snapshot.id,
        suggestion_type="next_action",
        content={"action": action_text, "proposed_patch": {"description_append": f"\n次のアクション: {action_text}"}},
        confidence=0.68 if data_sufficient else 0.3,
        rationale="タスクの状態、担当者、期限を基に、最小の前進となる操作を選びました。",
        features_used=features,
        references=references,
        expected_effect="着手条件を明確にし、停滞を減らします。",
        risks=["チーム固有の運用ルールが反映されていない可能性があります。"],
        inference_ms=round((time.perf_counter() - started) * 1000),
    )
    db.add_all([delay, action])
    await db.flush()
    return [delay, action]
