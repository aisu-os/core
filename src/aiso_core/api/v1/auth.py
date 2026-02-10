from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.database import get_db
from aiso_core.dependencies import get_current_user
from aiso_core.models.user import User
from aiso_core.schemas.user import RegisterResponse, TokenResponse, UserLogin, UserResponse
from aiso_core.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    email: str = Form(...),
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    avatar: UploadFile | None = File(None),
    avatar_emoji: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.register(
        email=email,
        username=username,
        display_name=display_name,
        password=password,
        avatar=avatar,
        avatar_emoji=avatar_emoji,
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.login(data)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
