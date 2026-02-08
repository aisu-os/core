from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.models.user import User
from aiso_core.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse
from aiso_core.utils.security import create_access_token, hash_password, verify_password


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: UserCreate) -> UserResponse:
        # Email mavjudligini tekshirish
        stmt = select(User).where(User.email == data.email)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu email allaqachon ro'yxatdan o'tgan",
            )

        # Username mavjudligini tekshirish
        stmt = select(User).where(User.username == data.username)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu username allaqachon band",
            )

        user = User(
            email=data.email,
            username=data.username,
            display_name=data.display_name,
            hashed_password=hash_password(data.password),
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        return UserResponse.model_validate(user)

    async def login(self, data: UserLogin) -> TokenResponse:
        stmt = select(User).where(User.email == data.email)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email yoki parol noto'g'ri",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Hisob faol emas",
            )

        access_token = create_access_token(data={"sub": str(user.id)})
        return TokenResponse(access_token=access_token)
