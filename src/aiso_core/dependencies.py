import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.database import get_db
from aiso_core.models.user import User
from aiso_core.utils.rate_limiter import get_rate_limiter
from aiso_core.utils.security import decode_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from err

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def rate_limit(limit: int, window_seconds: int) -> Callable[[Request], Awaitable[None]]:
    async def _check(request: Request) -> None:
        client_ip = _get_client_ip(request)
        key = f"{request.url.path}:{client_ip}"
        limiter = get_rate_limiter()
        await limiter.hit(key=key, limit=limit, window_seconds=window_seconds)

    return _check


def rate_limit_username_info() -> Callable[[Request], Awaitable[None]]:
    return rate_limit(
        limit=settings.rate_limit_username_info_per_minute,
        window_seconds=settings.rate_limit_window_seconds,
    )


def rate_limit_auth() -> Callable[[Request], Awaitable[None]]:
    return rate_limit(
        limit=settings.rate_limit_auth_per_minute,
        window_seconds=settings.rate_limit_window_seconds,
    )
