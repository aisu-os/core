from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.database import get_db
from aiso_core.dependencies import (
    get_current_user,
    rate_limit_auth,
    rate_limit_username_info,
)
from aiso_core.models.user import User
from aiso_core.schemas.user import (
    RegisterResponse,
    TokenResponse,
    UserLogin,
    UsernameInfoResponse,
    UserResponse,
)
from aiso_core.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    email: str = Form(...),
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    beta_token: str | None = Form(None),
    avatar: UploadFile | None = File(None),
    avatar_emoji: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_auth()),
):
    service = AuthService(db)
    return await service.register(
        email=email,
        username=username,
        display_name=display_name,
        password=password,
        beta_token=beta_token,
        avatar=avatar,
        avatar_emoji=avatar_emoji,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_auth()),
):
    service = AuthService(db)
    return await service.login(data)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.get("/username-info", response_model=UsernameInfoResponse)
async def get_username_info(
    username: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_username_info()),
):
    service = AuthService(db)
    return await service.get_username_info(username)
