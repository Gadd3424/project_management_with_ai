from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .domain.roles import MembershipStatus, OrganizationRole


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or len(normalized) > 320:
        raise ValueError("有効なメールアドレスを入力してください")
    return normalized


class InvitationCreate(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=120)
    role: OrganizationRole = OrganizationRole.MEMBER
    message: str = Field(default="", max_length=1000)

    _email = field_validator("email")(normalize_email)


class InvitationRead(BaseModel):
    id: str
    email: str
    display_name: str
    role: OrganizationRole
    expires_at: datetime
    development_token: str | None = None


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)


class DirectUserCreate(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=120)
    role: OrganizationRole = OrganizationRole.MEMBER

    _email = field_validator("email")(normalize_email)


class DirectUserRead(BaseModel):
    user_id: str
    temporary_password: str | None = None


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)


class RoleChange(BaseModel):
    role: OrganizationRole
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class StateChange(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    version: int = Field(ge=1)


class RestoreRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(default="復元", max_length=1000)


class OwnershipTransfer(BaseModel):
    new_owner_user_id: str
    current_user_password: str = Field(min_length=8, max_length=128)


class OrganizationUserRead(BaseModel):
    id: str
    email: str
    display_name: str
    role: OrganizationRole
    status: MembershipStatus
    last_login_at: datetime | None
    created_at: datetime
    version: int
    deleted_at: datetime | None


class OrganizationUserPage(BaseModel):
    items: list[OrganizationUserRead]
    page: int
    page_size: int
    total: int


class PermissionRead(BaseModel):
    role: OrganizationRole
    permissions: list[str]
