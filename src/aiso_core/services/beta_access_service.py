from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from urllib.parse import quote_plus

from fastapi import HTTPException, status
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.models.beta_access_request import BetaAccessRequest
from aiso_core.schemas.beta_access import BetaAccessRequestResponse

logger = logging.getLogger(__name__)

_email_adapter = TypeAdapter(EmailStr)


class BetaAccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalize_email(email: str) -> str:
        try:
            normalized = str(_email_adapter.validate_python(email))
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid email format",
            ) from err
        return normalized.strip().lower()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    async def create_request(self, email: str, extra_text: str | None) -> BetaAccessRequestResponse:
        normalized_email = self._normalize_email(email)
        now = datetime.now(UTC)
        token = secrets.token_urlsafe(24)
        token_hash = self._hash_token(token)
        token_expires_at = now + timedelta(hours=settings.beta_token_expire_hours)

        stmt = select(BetaAccessRequest).where(BetaAccessRequest.email == normalized_email)
        result = await self.db.execute(stmt)
        request = result.scalar_one_or_none()

        if request is None:
            request = BetaAccessRequest(
                email=normalized_email,
                extra_text=extra_text,
                token_hash=token_hash,
                token_expires_at=token_expires_at,
                token_used_at=None,
                email_sent_at=None,
            )
            self.db.add(request)
        else:
            request.extra_text = extra_text
            request.token_hash = token_hash
            request.token_expires_at = token_expires_at
            request.token_used_at = None

        await self._send_access_email(normalized_email, token)
        request.email_sent_at = now

        await self.db.flush()
        await self.db.refresh(request)

        return BetaAccessRequestResponse(
            request_id=request.id,
            message="Beta access link emailga yuborildi",
            token_expires_at=token_expires_at,
        )

    async def get_valid_request_or_raise(self, email: str, token: str | None) -> BetaAccessRequest:
        normalized_email = self._normalize_email(email)

        if not token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Beta access token is required",
            )

        stmt = select(BetaAccessRequest).where(BetaAccessRequest.email == normalized_email)
        result = await self.db.execute(stmt)
        request = result.scalar_one_or_none()

        if request is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Beta access request not found for this email",
            )

        if request.token_hash != self._hash_token(token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid beta access token",
            )

        now = datetime.now(UTC)
        if request.token_used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Beta access token already used",
            )

        if self._ensure_utc(request.token_expires_at) < now:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Beta access token expired",
            )

        return request

    async def mark_token_used(self, request: BetaAccessRequest) -> None:
        request.token_used_at = datetime.now(UTC)
        await self.db.flush()

    async def _send_access_email(self, recipient_email: str, token: str) -> None:
        register_link = (
            f"{settings.beta_register_url}?token={token}&email={quote_plus(recipient_email)}"
        )

        if not settings.smtp_host:
            # NOTE(beta): SMTP bo'lmasa local/test rejimda link logga chiqariladi.
            logger.warning(
                "SMTP is not configured; beta link was not emailed. recipient=%s link=%s",
                recipient_email,
                register_link,
            )
            return

        await asyncio.to_thread(self._send_access_email_sync, recipient_email, register_link)

    @staticmethod
    def _send_access_email_sync(recipient_email: str, register_link: str) -> None:
        message = EmailMessage()
        message["Subject"] = "Aisu Beta Access Link"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient_email
        message.set_content(
            "Siz Aisu beta access uchun so'rov yubordingiz. "
            f"Ro'yxatdan o'tish uchun bir martalik link: {register_link}"
        )

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()

                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)

                smtp.send_message(message)
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to send beta access email",
            ) from err
