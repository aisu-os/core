from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.database import async_session_factory
from aiso_core.models.user import User
from aiso_core.services.container_service import ContainerService, _get_docker_client
from aiso_core.services.terminal_service import TerminalSession
from aiso_core.utils.security import decode_token

logger = logging.getLogger(__name__)

router = APIRouter()


async def _authenticate_ws(token: str | None, db: AsyncSession) -> User | None:
    """WebSocket token dan user olish."""
    if not token:
        return None

    payload = decode_token(token)
    if payload is None:
        return None

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        return None

    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError:
        return None

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        return None

    return user


@router.websocket("/terminal")
async def terminal_ws(websocket: WebSocket, token: str | None = None) -> None:
    """Terminal WebSocket endpoint.

    Oqim:
    1. Token auth
    2. Container running tekshirish / ishga tushirish
    3. Docker exec session yaratish
    4. Bi-directional I/O loop
    """
    async with async_session_factory() as db:
        user = await _authenticate_ws(token, db)
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()
        logger.debug("Terminal WS accepted: user_id=%s", user.id)

        # Container holatini tekshirish va ishga tushirish
        container_name = f"aisu_{user.id}"
        try:
            await websocket.send_json({"type": "status", "status": "starting-container"})

            container_svc = ContainerService(db)
            result = await container_svc.start_container(
                user_id=user.id,
                cpu=user.cpu,
                disk_mb=user.disk,
            )
            await db.commit()

            if result["status"] != "running":
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Container ishga tushmadi",
                    }
                )
                await websocket.close()
                return

            # Yangi yaratilgan yoki qayta ishga tushirilgan container tayyor bo'lishini kutish
            was_reprovisioned = "provisioned" in result.get("message", "")
            if was_reprovisioned:

                def _wait_for_ready() -> None:
                    """Container to'liq tayyor bo'lguncha kutish."""
                    import time

                    client = _get_docker_client()
                    for _ in range(20):
                        try:
                            c = client.containers.get(container_name)
                            if c.status == "running":
                                return
                        except Exception:
                            pass
                        time.sleep(0.25)

                await asyncio.to_thread(_wait_for_ready)
                await asyncio.sleep(0.5)

        except WebSocketDisconnect:
            logger.info("Container start paytida klient uzildi: user_id=%s", user.id)
            return
        except Exception:
            logger.exception("Container start xatolik: user_id=%s", user.id)
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Container xatolik",
                    }
                )
                await websocket.close()
            except Exception:
                pass
            return
        logger.debug("Container ready, creating exec session...")
        session = TerminalSession(container_name)

        try:
            await session.start()
            logger.debug("Exec session started: %s", session.session_id)
        except Exception:
            logger.exception("Terminal session start xatolik: user_id=%s", user.id)
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Terminal sessiya yaratib bo'lmadi",
                    }
                )
                await websocket.close()
            except Exception:
                pass
            return

        await websocket.send_json(
            {
                "type": "ready",
                "sessionId": session.session_id,
            }
        )
        logger.debug("'ready' sent, starting I/O loop")

        # Bi-directional I/O
        async def read_from_container() -> None:
            """Container dan o'qib, WebSocket ga yozish."""
            try:
                while not session.is_closed:
                    data = await session.read()
                    if not data:
                        # Container to'xtagan bo'lishi mumkin — tekshirish
                        reason = "Docker exec yopildi"
                        try:

                            def _check_container() -> str:
                                client = _get_docker_client()
                                c = client.containers.get(container_name)
                                if c.status != "running":
                                    logs = c.logs(tail=3).decode().strip()
                                    return f"Container to'xtadi ({c.status}): {logs}"
                                return "Docker exec EOF"

                            reason = await asyncio.to_thread(_check_container)
                        except Exception:
                            pass
                        logger.debug("read: EOF — %s", reason)
                        with contextlib.suppress(Exception):
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": reason,
                                }
                            )
                        break
                    await websocket.send_bytes(data)
            except WebSocketDisconnect:
                logger.debug("read: client disconnected")
            except Exception:
                logger.debug("read: exception", exc_info=True)

        async def write_to_container() -> None:
            """WebSocket dan o'qib, container ga yozish."""
            try:
                while not session.is_closed:
                    message = await websocket.receive()

                    if message.get("type") == "websocket.disconnect":
                        logger.debug("write: websocket disconnect received")
                        break

                    if "bytes" in message and message["bytes"]:
                        await session.write(message["bytes"])
                    elif "text" in message and message["text"]:
                        try:
                            control = json.loads(message["text"])
                            if control.get("type") == "resize":
                                rows = control.get("rows", 24)
                                cols = control.get("cols", 80)
                                await session.resize(rows, cols)
                        except json.JSONDecodeError:
                            await session.write(message["text"].encode("utf-8"))
            except WebSocketDisconnect:
                logger.debug("write: client disconnected")
            except Exception:
                logger.debug("write: exception", exc_info=True)

        try:
            read_task = asyncio.create_task(read_from_container())
            write_task = asyncio.create_task(write_to_container())
            done, pending = await asyncio.wait(
                [read_task, write_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            finished = done.pop()
            which = "read" if finished is read_task else "write"
            logger.debug("Session ended: %s task finished first", which)
            for task in pending:
                task.cancel()
        finally:
            logger.debug("Cleaning up session + websocket")
            await session.close()
            with contextlib.suppress(Exception):
                await websocket.close()
