from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class OrganizationMember(Base, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="todo")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class FeatureSnapshot(Base, TimestampMixin):
    __tablename__ = "feature_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSON)
    schema_version: Mapped[str] = mapped_column(String(40), default="task-v1")


class ModelArtifact(Base, TimestampMixin):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    model_version: Mapped[str] = mapped_column(String(60))
    base_model_id: Mapped[str] = mapped_column(String(255))
    parent_model_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    artifact_path: Mapped[str] = mapped_column(String(500))
    checksum: Mapped[str] = mapped_column(String(64))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approval_status: Mapped[str] = mapped_column(String(30), default="pending")
    deployment_status: Mapped[str] = mapped_column(String(30), default="not_deployed")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AISuggestion(Base, TimestampMixin):
    __tablename__ = "ai_suggestions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    feature_snapshot_id: Mapped[str] = mapped_column(ForeignKey("feature_snapshots.id"))
    model_id: Mapped[str | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    suggestion_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    features_used: Mapped[dict[str, Any]] = mapped_column(JSON)
    references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    expected_effect: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision: Mapped[str] = mapped_column(String(30), default="pending")
    revised_content: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    inference_ms: Mapped[int] = mapped_column(Integer, default=0)


class AISuggestionFeedback(Base, TimestampMixin):
    __tablename__ = "ai_suggestion_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    suggestion_id: Mapped[str] = mapped_column(ForeignKey("ai_suggestions.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    actual_outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ModelExperiment(Base, TimestampMixin):
    __tablename__ = "model_experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    algorithm: Mapped[str] = mapped_column(String(40), default="genetic_algorithm")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON)
    random_seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    checkpoint_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class ModelCandidate(Base, TimestampMixin):
    __tablename__ = "model_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("model_experiments.id"), index=True)
    parent_model_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    genome: Mapped[dict[str, Any]] = mapped_column(JSON)
    generation: Mapped[int] = mapped_column(Integer)
    fitness: Mapped[float | None] = mapped_column(Float, nullable=True)
    individual_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    correlation_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", "method", "path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
