from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .domain.roles import MembershipStatus, OrganizationRole, UserStatus


def enum_values(enum_class):
    return [item.value for item in enum_class]


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
    status: Mapped[UserStatus] = mapped_column(
        SqlEnum(UserStatus, values_callable=enum_values, native_enum=False, length=20),
        default=UserStatus.ACTIVE,
    )
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=1)
    force_password_change: Mapped[bool] = mapped_column(Boolean, default=False)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    allow_admin_manage_admins: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_direct_user_creation: Mapped[bool] = mapped_column(Boolean, default=False)
    invitation_expiry_hours: Mapped[int] = mapped_column(Integer, default=72)


class OrganizationMember(Base, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[OrganizationRole] = mapped_column(
        SqlEnum(OrganizationRole, values_callable=enum_values, native_enum=False, length=20),
        default=OrganizationRole.MEMBER,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        SqlEnum(MembershipStatus, values_callable=enum_values, native_enum=False, length=20),
        default=MembershipStatus.ACTIVE,
    )
    invited_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class UserInvitation(Base, TimestampMixin):
    __tablename__ = "user_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[OrganizationRole] = mapped_column(
        SqlEnum(OrganizationRole, values_callable=enum_values, native_enum=False, length=20)
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    success_criteria: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class ProjectAISuggestion(Base, TimestampMixin):
    __tablename__ = "project_ai_suggestions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    suggestion_type: Mapped[str] = mapped_column(String(50))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    proposed_values: Mapped[dict[str, Any]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_effect: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    model_id: Mapped[str | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    inference_ms: Mapped[int] = mapped_column(Integer, default=0)
    decision: Mapped[str] = mapped_column(String(30), default="pending")
    feedback_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_comment: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
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
    target_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    previous_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    new_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String(20), default="success")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
