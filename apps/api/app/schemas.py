from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class UserRead(ORMModel):
    id: str
    email: str
    display_name: str
    force_password_change: bool = False


class LoginResponse(BaseModel):
    user: UserRead
    access_token: str
    token_type: str = "bearer"
    csrf_token: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    objective: str = Field(default="", max_length=10000)
    success_criteria: str = Field(default="", max_length=10000)
    start_date: datetime | None = None
    due_date: datetime | None = None
    status: Literal["active", "archived"] = "active"
    ai_suggestion_id: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    objective: str | None = Field(default=None, max_length=10000)
    success_criteria: str | None = Field(default=None, max_length=10000)
    start_date: datetime | None = None
    due_date: datetime | None = None
    status: Literal["active", "archived"] | None = None
    ai_suggestion_id: str | None = None
    version: int = Field(ge=1)


class ProjectRead(ORMModel):
    id: str
    organization_id: str
    name: str
    description: str
    objective: str
    success_criteria: str
    start_date: datetime | None
    due_date: datetime | None
    status: str
    version: int
    created_at: datetime


class ProjectDefaultsRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class ProjectDeleteRequest(BaseModel):
    version: int = Field(ge=1)


class ProjectAISuggestionRead(ORMModel):
    id: str
    project_id: str | None
    suggestion_type: str
    proposed_values: dict[str, Any]
    confidence: float
    rationale: str
    evidence: list[dict[str, Any]]
    assumptions: list[str]
    risks: list[str]
    expected_effect: str
    provider: str
    model_id: str | None
    model_version: str | None
    inference_ms: int
    decision: str
    created_at: datetime


class ProjectAIFeedback(BaseModel):
    decision: Literal["accepted", "rejected", "modified"]
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str = Field(default="", max_length=5000)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    status: Literal["todo", "in_progress", "review", "done"] = "todo"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    assignee_id: str | None = None
    due_at: datetime | None = None
    parent_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    status: Literal["todo", "in_progress", "review", "done"] | None = None
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    assignee_id: str | None = None
    due_at: datetime | None = None
    position: int | None = Field(default=None, ge=0)
    version: int = Field(ge=1)


class TaskRead(ORMModel):
    id: str
    project_id: str
    title: str
    description: str
    status: str
    priority: str
    assignee_id: str | None
    due_at: datetime | None
    position: int
    version: int
    created_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class CommentRead(ORMModel):
    id: str
    task_id: str
    body: str
    created_by: str
    created_at: datetime


class SuggestionRead(ORMModel):
    id: str
    task_id: str
    suggestion_type: str
    content: dict[str, Any]
    confidence: float
    rationale: str
    features_used: dict[str, Any]
    references: list[dict[str, Any]]
    expected_effect: str
    risks: list[str]
    decision: str
    revised_content: dict[str, Any] | None
    inference_ms: int
    created_at: datetime


class SuggestionDecision(BaseModel):
    revised_content: dict[str, Any] | None = None


class FeedbackCreate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str = Field(default="", max_length=5000)
    actual_outcome: dict[str, Any] | None = None


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    adapter_paths: list[str] = Field(min_length=2, max_length=8)
    population_size: int = Field(default=8, ge=4, le=100)
    generations: int = Field(default=5, ge=1, le=100)
    random_seed: int = 42
    evaluation_dataset_version: str = Field(default="project-proposals-v1", max_length=100)
    prompt_version: str = Field(default="project-ai-v1", max_length=100)


class ExperimentRead(ORMModel):
    id: str
    name: str
    algorithm: str
    configuration: dict[str, Any]
    random_seed: int
    status: str
    progress: float
    cancel_requested: bool
    checkpoint_path: str | None
    created_at: datetime

