import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_serializer

from aiso_core.utils.helpers import with_full_url


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    display_name: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    display_name: str
    avatar_url: str | None = None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("avatar_url")
    def _serialize_avatar_url(self, value: str | None) -> str | None:
        return with_full_url(value)


class RegisterResponse(BaseModel):
    username: str
    display_name: str
    avatar_url: str | None = None
    wallpaper: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsernameInfoResponse(BaseModel):
    avatar_url: str | None = None
    display_name: str
    wallpaper: str

    model_config = {"from_attributes": True}

    @field_serializer("avatar_url")
    def _serialize_avatar_url(self, value: str | None) -> str | None:
        return with_full_url(value)
