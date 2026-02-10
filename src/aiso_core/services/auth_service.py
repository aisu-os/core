import uuid

from fastapi import HTTPException, UploadFile, status
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.models.user import User
from aiso_core.schemas.user import (
    RegisterResponse,
    TokenResponse,
    UserLogin,
    UsernameInfoResponse,
)
from aiso_core.utils.file_upload import save_avatar
from aiso_core.utils.helpers import with_full_url
from aiso_core.utils.security import create_access_token, hash_password, verify_password

_email_adapter = TypeAdapter(EmailStr)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self,
        email: str,
        username: str,
        display_name: str,
        password: str,
        avatar: UploadFile | None = None,
        avatar_emoji: str | None = None,
    ) -> RegisterResponse:
        # Email formatini tekshirish
        try:
            _email_adapter.validate_python(email)
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid email format",
            ) from err

        # Email mavjudligini tekshirish
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already registered",
            )

        # Username mavjudligini tekshirish
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken",
            )

        user_id = uuid.uuid4()

        # Avatar URL aniqlash
        avatar_url: str | None = None
        if avatar and avatar.filename:
            avatar_url = await save_avatar(avatar, user_id, settings.upload_dir)
        elif avatar_emoji:
            avatar_url = avatar_emoji

        user = User(
            id=user_id,
            email=email,
            username=username,
            display_name=display_name,
            hashed_password=hash_password(password),
            avatar_url=avatar_url,
            cpu=settings.default_user_cpu,
            disk=settings.default_user_disk,
            wallpaper=settings.default_user_wallpaper,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        return RegisterResponse(
            username=user.username,
            display_name=user.display_name,
            avatar_url=with_full_url(user.avatar_url),
            wallpaper=user.wallpaper,
        )

    async def login(self, data: UserLogin) -> TokenResponse:
        stmt = select(User).where(User.username == data.username)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        access_token = create_access_token(data={"sub": str(user.id)})
        return TokenResponse(access_token=access_token)

    async def get_username_info(self, username: str) -> UsernameInfoResponse:
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UsernameInfoResponse(
            avatar_url=user.avatar_url,
            display_name=user.display_name,
            wallpaper=user.wallpaper,
        )
