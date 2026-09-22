from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import Comment, ModelArtifact, Project, Task


def _defaults(name: str) -> dict[str, Any]:
    normalized = name.lower()
    category = "業務改善"
    duration = 90
    if any(word in normalized for word in ("ai", "人工知能", "ml", "モデル")):
        category, duration = "AI活用", 120
    elif any(word in normalized for word in ("web", "サイト", "アプリ", "システム")):
        category, duration = "システム開発", 90
    elif any(word in normalized for word in ("採用", "人事", "研修")):
        category, duration = "組織開発", 60
    today = datetime.now(UTC).date()
    return {
        "description": f"{name}を計画・実行し、関係者が進捗と判断根拠を共有できる状態を作ります。",
        "objective": f"{category}の取り組みとして、{name}の価値を検証し、継続可能な運用へ移行すること。",
        "success_criteria": "主要成果物が受け入れ基準を満たし、期限・担当・次のアクションが明確になっていること。",
        "start_date": today.isoformat(),
        "due_date": (today + timedelta(days=duration)).isoformat(),
        "status": "active",
    }


def mock_defaults(name: str) -> dict[str, Any]:
    started = time.perf_counter()
    return {
        "proposed_values": _defaults(name),
        "confidence": 0.72,
        "rationale": "プロジェクト名の分野キーワードと一般的な立ち上げ期間から初期案を生成しました。",
        "evidence": [{"type": "project_name", "value": name}],
        "assumptions": ["開始日は本日を想定しています。", "組織固有の休日と承認期間は未反映です。"],
        "risks": ["実際のスコープと体制に応じて期限と成功条件を調整してください。"],
        "expected_effect": "空欄から作成する負担を減らし、目的と完了条件の確認を促します。",
        "provider": "mock",
        "model_id": None,
        "model_version": None,
        "inference_ms": round((time.perf_counter() - started) * 1000),
    }


async def project_snapshot(db: AsyncSession, project: Project) -> dict[str, Any]:
    tasks = list(
        (
            await db.scalars(
                select(Task).where(
                    Task.organization_id == project.organization_id,
                    Task.project_id == project.id,
                    Task.deleted_at.is_(None),
                )
            )
        ).all()
    )
    counts = {
        status: sum(task.status == status for task in tasks) for status in ("todo", "in_progress", "on_hold", "done")
    }
    now = datetime.now(UTC)
    overdue = sum(
        bool(
            task.due_at
            and (task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)) < now
            and task.status != "done"
        )
        for task in tasks
    )
    comments = await db.scalar(
        select(func.count(Comment.id))
        .join(Task, Comment.task_id == Task.id)
        .where(
            Task.project_id == project.id,
            Comment.organization_id == project.organization_id,
            Comment.deleted_at.is_(None),
        )
    )
    return {
        "project": {
            "name": project.name,
            "description": project.description,
            "objective": project.objective,
            "success_criteria": project.success_criteria,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "due_date": project.due_date.isoformat() if project.due_date else None,
            "status": project.status,
            "version": project.version,
        },
        "metrics": {
            "task_count": len(tasks),
            "status_counts": counts,
            "completion_rate": round(counts["done"] / len(tasks), 3) if tasks else 0.0,
            "overdue_count": overdue,
            "high_priority_count": sum(task.priority in {"high", "urgent"} for task in tasks),
            "unassigned_count": sum(not task.assignee_id and task.status != "done" for task in tasks),
            "comment_count": int(comments or 0),
        },
    }


def mock_change_proposal(snapshot: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    project = snapshot["project"]
    metrics = snapshot["metrics"]
    changes: dict[str, Any] = {}
    if not project["objective"]:
        changes["objective"] = f"{project['name']}の成果を明確化し、計画に沿って価値を提供すること。"
    if not project["success_criteria"]:
        changes["success_criteria"] = "全タスクの完了条件が確認され、主要成果物が関係者に受け入れられていること。"
    if metrics["task_count"] and metrics["completion_rate"] == 1:
        changes["status"] = "archived"
    elif metrics["overdue_count"]:
        changes["description"] = (
            project["description"].rstrip()
            + f"\n\n進捗メモ: 期限超過タスクが{metrics['overdue_count']}件あります。期限と担当を再確認してください。"
        ).strip()
        current_due = datetime.fromisoformat(project["due_date"]) if project["due_date"] else datetime.now(UTC)
        changes["due_date"] = (current_due + timedelta(days=14)).date().isoformat()
    return {
        "proposed_values": changes,
        "confidence": 0.82 if metrics["task_count"] else 0.45,
        "rationale": "タスクの完了率、期限超過、優先度、担当者設定を基に、必要最小限の変更案を作成しました。",
        "evidence": [{"type": "project_metrics", **metrics}],
        "assumptions": ["期限延長案は再計画の起点であり、確定日ではありません。"],
        "risks": ["タスク外で管理されている依存関係は反映されていません。"],
        "expected_effect": "現在の状況とプロジェクト定義のずれを小さくします。",
        "provider": "mock",
        "model_id": None,
        "model_version": None,
        "inference_ms": round((time.perf_counter() - started) * 1000),
    }


def mock_task_suggestions(snapshot: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    name = snapshot["name"]
    objective = snapshot["objective"]
    success = snapshot["success_criteria"]
    due_date = snapshot.get("due_date")
    tasks = [
        {
            "title": "要件と成功条件を合意する",
            "description": f"{name}の目的と成果物の受け入れ基準を関係者と確認します。",
            "notes": f"目的: {objective}\n成功条件: {success}",
            "priority": "high",
            "due_at": None,
            "rationale": "実行前に目的と完了条件の認識差を解消するためです。",
            "confidence": 0.88,
            "assumptions": ["主要な関係者を特定できること。"],
        },
        {
            "title": "実行計画と担当を整理する",
            "description": "成果物を作業単位に分解し、担当、期限、依存関係を明確にします。",
            "notes": "計画承認後に各タスクの担当者を設定してください。",
            "priority": "high",
            "due_at": None,
            "rationale": "作業の抜け漏れと担当の曖昧さを減らすためです。",
            "confidence": 0.84,
            "assumptions": ["実行メンバーが確定していること。"],
        },
        {
            "title": "主要成果物を作成する",
            "description": f"{success}を満たす主要成果物を作成し、レビュー可能な状態にします。",
            "notes": "成果物の具体的な内訳は計画時に追記してください。",
            "priority": "medium",
            "due_at": due_date,
            "rationale": "成功条件に直接つながる実行タスクが必要なためです。",
            "confidence": 0.8,
            "assumptions": ["成功条件が成果物として検証可能であること。"],
        },
        {
            "title": "受け入れ確認と振り返りを行う",
            "description": "成功条件に照らして成果を確認し、残課題と次のアクションを記録します。",
            "notes": "未達項目は保留理由と再計画を残してください。",
            "priority": "medium",
            "due_at": due_date,
            "rationale": "完了判定を明確にし、学びを次の活動へつなげるためです。",
            "confidence": 0.82,
            "assumptions": ["受け入れ判断を行う責任者がいること。"],
        },
    ]
    return {
        "proposed_values": {"tasks": tasks},
        "confidence": 0.83,
        "rationale": "プロジェクトの目的と成功条件から、立ち上げ、実行、受け入れに必要な初期タスクを生成しました。",
        "evidence": [
            {"type": "project_objective", "value": objective},
            {"type": "success_criteria", "value": success},
        ],
        "assumptions": ["提案は初期計画であり、担当者と依存関係はユーザーが確認します。"],
        "risks": ["組織固有の承認工程や外部依存は提案に含まれない場合があります。"],
        "expected_effect": "目的と成功条件に沿った初期計画を短時間で作成できます。",
        "provider": "mock",
        "model_id": None,
        "model_version": None,
        "inference_ms": round((time.perf_counter() - started) * 1000),
    }


async def _active_model(db: AsyncSession, organization_id: str) -> ModelArtifact | None:
    return await db.scalar(
        select(ModelArtifact)
        .where(
            (ModelArtifact.organization_id == organization_id) | (ModelArtifact.organization_id.is_(None)),
            ModelArtifact.approval_status == "approved",
            ModelArtifact.deployment_status == "active",
        )
        .order_by(ModelArtifact.created_at.desc())
    )


async def _infer(
    db: AsyncSession, organization_id: str, path: str, payload: dict[str, Any], fallback
) -> dict[str, Any]:
    settings = get_settings()
    model = await _active_model(db, organization_id)
    if settings.ai_provider == "mock" or not model:
        result = fallback()
        if not model:
            result["risks"].append("承認済みの進化的マージモデルが未配備のため、mock提案を使用しました。")
        return result
    request_payload = {
        **payload,
        "model": {
            "id": model.id,
            "version": model.model_version,
            "artifact_path": model.artifact_path,
            "checksum": model.checksum,
            "metrics": model.metrics,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=settings.inference_timeout_seconds) as client:
            response = await client.post(f"{settings.inference_url}{path}", json=request_payload)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        if not settings.ai_allow_mock_fallback:
            raise
        result = fallback()
        result["risks"].append("進化的マージモデルの推論に失敗したため、mockへフォールバックしました。")
        return result


async def suggest_defaults(db: AsyncSession, organization_id: str, name: str) -> dict[str, Any]:
    return await _infer(db, organization_id, "/v1/projects/defaults", {"name": name}, lambda: mock_defaults(name))


async def suggest_changes(db: AsyncSession, project: Project) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = await project_snapshot(db, project)
    result = await _infer(
        db,
        project.organization_id,
        "/v1/projects/change-proposal",
        {"snapshot": snapshot},
        lambda: mock_change_proposal(snapshot),
    )
    return snapshot, result


async def suggest_initial_tasks(
    db: AsyncSession, organization_id: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    return await _infer(
        db,
        organization_id,
        "/v1/projects/task-suggestions",
        {"snapshot": snapshot},
        lambda: mock_task_suggestions(snapshot),
    )
