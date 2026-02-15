"""Terminal WebSocket endpoint va TerminalSession testlari.

Mock Docker socket bilan ishlaydi — haqiqiy Docker kerak emas.
GNU screen yondashuvini test qiladi.
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aiso_core.config import settings
from aiso_core.models.user import User
from aiso_core.services.terminal_service import TerminalSession, _extract_socket
from aiso_core.utils.security import create_access_token

# ── Fixtures ──


@pytest.fixture
def mock_socket() -> MagicMock:
    """Mock socket — recv() va sendall() simulyatsiya qiladi."""
    sock = MagicMock(spec=socket.socket)
    sock.fileno.return_value = 5
    recv_data = [b"aisu@aisu:~$ "]
    call_count = 0

    def mock_recv(size: int) -> bytes:
        nonlocal call_count
        if call_count < len(recv_data):
            data = recv_data[call_count]
            call_count += 1
            return data
        time.sleep(100)
        return b""

    sock.recv = mock_recv
    sock.sendall = MagicMock()
    sock.settimeout = MagicMock()
    return sock


@pytest.fixture
def mock_docker_client(mock_socket: MagicMock) -> MagicMock:
    """Mock Docker client — screen oqimini simulyatsiya qiladi."""
    client = MagicMock()

    # exec_create har safar yangi ID qaytaradi
    # 3 ta exec: screenrc yaratish + screen create + screen attach
    exec_ids = iter(
        [
            "exec_screenrc_setup",
            "exec_screen_create_123",
            "exec_screen_attach_456",
        ]
    )
    client.api.exec_create.side_effect = lambda *a, **kw: {"Id": next(exec_ids)}

    # exec_start natijalari:
    # 1. screenrc yaratish -> bytes output
    # 2. screen -dmS (create) -> bytes output
    # 3. screen -r (attach) -> socket wrapper
    socket_wrapper = MagicMock()
    socket_wrapper._sock = mock_socket

    start_results = iter([b"", b"", socket_wrapper])
    client.api.exec_start.side_effect = lambda *a, **kw: next(start_results)

    # exec_inspect (screen create natijasi)
    client.api.exec_inspect.return_value = {"ExitCode": 0, "Running": False}

    client.api.exec_resize.return_value = None

    container_mock = MagicMock()
    container_mock.status = "running"
    client.containers.get.return_value = container_mock

    return client


# ── TerminalSession testlari ──


class TestTerminalSession:
    async def test_start_creates_screen_and_attaches(
        self,
        mock_docker_client: MagicMock,
        mock_socket: MagicMock,
    ) -> None:
        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()

            assert session._exec_id == "exec_screen_attach_456"
            assert session._raw_socket is mock_socket
            assert not session.is_closed

            # exec_create 3 marta chaqirilishi kerak (screenrc + screen create + screen attach)
            assert mock_docker_client.api.exec_create.call_count == 3

            # Birinchi — screenrc yaratish (bash -c ...)
            first_call = mock_docker_client.api.exec_create.call_args_list[0]
            first_cmd = first_call[1]["cmd"]
            assert first_cmd[0] == "bash"
            assert first_cmd[1] == "-c"

            # Ikkinchi — screen -dmS (session yaratish)
            second_call = mock_docker_client.api.exec_create.call_args_list[1]
            second_cmd = second_call[1]["cmd"]
            assert second_cmd[0] == "screen"
            assert "-dmS" in second_cmd

            # Uchinchi — screen -r (attach)
            third_call = mock_docker_client.api.exec_create.call_args_list[2]
            third_cmd = third_call[1]["cmd"]
            assert third_cmd[0] == "screen"
            assert "-r" in third_cmd

    async def test_read_returns_data(
        self,
        mock_docker_client: MagicMock,
    ) -> None:
        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()

            data = await session.read()
            assert data == b"aisu@aisu:~$ "

    async def test_write_sends_data(
        self,
        mock_docker_client: MagicMock,
        mock_socket: MagicMock,
    ) -> None:
        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()

            await session.write(b"ls\n")
            mock_socket.sendall.assert_called_once_with(b"ls\n")

    async def test_write_after_close_is_noop(
        self,
        mock_docker_client: MagicMock,
        mock_socket: MagicMock,
    ) -> None:
        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()
            await session.close()

            await session.write(b"ls\n")
            mock_socket.sendall.assert_not_called()

    async def test_read_after_close_returns_empty(
        self,
        mock_docker_client: MagicMock,
    ) -> None:
        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()
            await session.close()

            data = await session.read()
            assert data == b""

    async def test_close_is_idempotent(
        self,
        mock_docker_client: MagicMock,
    ) -> None:
        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()
            await session.close()
            await session.close()
            assert session.is_closed

    async def test_resize_calls_docker_api(
        self,
        mock_docker_client: MagicMock,
    ) -> None:
        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()

            await session.resize(40, 120)
            mock_docker_client.api.exec_resize.assert_called_once_with(
                "exec_screen_attach_456",
                height=40,
                width=120,
            )

    async def test_read_oserror_when_closed_returns_empty(
        self,
        mock_docker_client: MagicMock,
    ) -> None:
        bad_socket = MagicMock(spec=socket.socket)
        bad_socket.recv.side_effect = OSError("Connection reset")
        bad_socket.settimeout = MagicMock()

        socket_wrapper = MagicMock()
        socket_wrapper._sock = bad_socket
        mock_docker_client.api.exec_start.side_effect = [b"", b"", socket_wrapper]
        mock_docker_client.api.exec_create.side_effect = [
            {"Id": "e1"},
            {"Id": "e2"},
            {"Id": "e3"},
        ]

        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()
            session._closed = True

            data = await session.read()
            assert data == b""

    async def test_read_oserror_when_open_raises(
        self,
        mock_docker_client: MagicMock,
    ) -> None:
        bad_socket = MagicMock(spec=socket.socket)
        bad_socket.recv.side_effect = OSError("Connection reset")
        bad_socket.settimeout = MagicMock()

        socket_wrapper = MagicMock()
        socket_wrapper._sock = bad_socket
        mock_docker_client.api.exec_start.side_effect = [b"", b"", socket_wrapper]
        mock_docker_client.api.exec_create.side_effect = [
            {"Id": "e1"},
            {"Id": "e2"},
            {"Id": "e3"},
        ]

        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            await session.start()

            with pytest.raises(OSError, match="Connection reset"):
                await session.read()

    async def test_session_id_is_unique(self) -> None:
        s1 = TerminalSession("c1")
        s2 = TerminalSession("c2")
        assert s1.session_id != s2.session_id

    async def test_custom_session_id(self) -> None:
        s = TerminalSession("c1", session_id="my-id")
        assert s.session_id == "my-id"
        assert s._screen_session == "term_my-id"

    async def test_screen_session_failed_raises(
        self,
        mock_docker_client: MagicMock,
    ) -> None:
        """screen yaratilmasa RuntimeError ko'tarilishi kerak."""
        mock_docker_client.api.exec_inspect.return_value = {"ExitCode": 1}
        # screenrc yaratish muvaffaqiyatli, lekin screen create muvaffaqiyatsiz
        mock_docker_client.api.exec_create.side_effect = [
            {"Id": "e_screenrc"},
            {"Id": "e1"},
        ]
        mock_docker_client.api.exec_start.side_effect = [b"", b"no screen running"]

        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            with pytest.raises(RuntimeError, match="screen session yaratib bo'lmadi"):
                await session.start()


class TestExtractSocket:
    def test_extracts_from_sock_attribute(self) -> None:
        raw = MagicMock(spec=socket.socket)
        wrapper = MagicMock()
        wrapper._sock = raw
        assert _extract_socket(wrapper) is raw

    def test_extracts_from_fileno_wrapper(self) -> None:
        wrapper = MagicMock()
        del wrapper._sock
        wrapper.fileno.return_value = 5
        result = _extract_socket(wrapper)
        assert result is wrapper

    def test_raises_for_unknown_type(self) -> None:
        wrapper = object()
        with pytest.raises(RuntimeError, match="Docker socket olishda xatolik"):
            _extract_socket(wrapper)

    def test_nested_sock_with_fileno(self) -> None:
        """Ichma-ich wrapper — _sock.fileno() bor lekin socket.socket emas."""
        inner = MagicMock()
        inner.fileno.return_value = 7
        del inner.family
        wrapper = MagicMock()
        wrapper._sock = inner
        result = _extract_socket(wrapper)
        assert result is inner


# ── WebSocket endpoint testlari ──


class TestTerminalWebSocket:
    """Terminal WebSocket endpoint integratsiya testlari."""

    @pytest.fixture
    async def user_and_token(
        self,
        db_session: AsyncSession,
    ) -> tuple[User, str]:
        user = User(
            id=uuid.uuid4(),
            email="terminal_test@test.com",
            username="terminal_test",
            display_name="Terminal Test",
            hashed_password="$2b$12$dummy_hash_for_test",
            role="user",
            is_active=True,
            cpu=2,
            disk=5120,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token({"sub": str(user.id)})
        return user, token

    @pytest.fixture
    def mock_terminal_session(self) -> MagicMock:
        """Barqaror mock TerminalSession."""
        session = AsyncMock(spec=TerminalSession)
        session.session_id = "test-session-123"
        session.is_closed = False

        read_queue: asyncio.Queue[bytes] = asyncio.Queue()
        read_queue.put_nowait(b"aisu@aisu:~$ ")

        async def mock_read(size: int = 4096) -> bytes:
            if session.is_closed:
                return b""
            try:
                return await asyncio.wait_for(read_queue.get(), timeout=30.0)
            except TimeoutError:
                return b""

        session.read = mock_read

        async def mock_write(data: bytes) -> None:
            if not session.is_closed:
                await read_queue.put(data)
                if data == b"\r" or data.endswith(b"\n"):
                    await read_queue.put(b"\r\naisu@aisu:~$ ")

        session.write = mock_write
        session.start = AsyncMock()
        session.close = AsyncMock()
        session.resize = AsyncMock()
        session._read_queue = read_queue
        return session

    def _setup_ws_test(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_terminal_session: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """WebSocket test uchun umumiy setup — monkeypatch + mock."""
        from aiso_core.main import app

        monkeypatch.setattr(settings, "container_enabled", False)

        monkeypatch.setattr(
            "aiso_core.api.v1.terminal.async_session_factory",
            async_session_factory,
        )

        mock_container_instance = AsyncMock()
        mock_container_instance.start_container.return_value = {
            "status": "running",
            "message": "ok",
        }

        mock_docker_container = MagicMock()
        mock_docker_container.status = "running"
        mock_docker_client_obj = MagicMock()
        mock_docker_client_obj.containers.get.return_value = mock_docker_container

        patches = [
            patch(
                "aiso_core.api.v1.terminal.ContainerService",
                return_value=mock_container_instance,
            ),
            patch(
                "aiso_core.api.v1.terminal.TerminalSession",
                return_value=mock_terminal_session,
            ),
            patch(
                "aiso_core.api.v1.terminal._get_docker_client",
                return_value=mock_docker_client_obj,
            ),
        ]
        return app, patches

    async def test_no_token_rejects(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from starlette.testclient import TestClient

        from aiso_core.main import app

        monkeypatch.setattr(settings, "container_enabled", False)
        monkeypatch.setattr(
            "aiso_core.api.v1.terminal.async_session_factory",
            async_session_factory,
        )

        with TestClient(app) as tc, pytest.raises(Exception):
            with tc.websocket_connect("/ws/terminal"):
                pass

    async def test_invalid_token_rejects(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from starlette.testclient import TestClient

        from aiso_core.main import app

        monkeypatch.setattr(settings, "container_enabled", False)
        monkeypatch.setattr(
            "aiso_core.api.v1.terminal.async_session_factory",
            async_session_factory,
        )

        with TestClient(app) as tc, pytest.raises(Exception):
            with tc.websocket_connect("/ws/terminal?token=invalid_token"):
                pass

    async def test_full_session_lifecycle(
        self,
        user_and_token: tuple[User, str],
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_terminal_session: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """To'liq sessiya: connect → ready → input → output → disconnect."""
        _, token = user_and_token
        app, patches = self._setup_ws_test(
            async_session_factory,
            mock_terminal_session,
            monkeypatch,
        )

        from starlette.testclient import TestClient

        with patches[0], patches[1], patches[2], TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/terminal?token={token}") as ws:
                msg1 = ws.receive_json()
                assert msg1["type"] == "status"
                assert msg1["status"] == "starting-container"

                msg2 = ws.receive_json()
                assert msg2["type"] == "ready"
                assert "sessionId" in msg2

                prompt = ws.receive_bytes()
                assert b"aisu" in prompt

                ws.send_bytes(b"l")
                echo = ws.receive_bytes()
                assert echo == b"l"

                ws.send_text(json.dumps({"type": "resize", "rows": 40, "cols": 120}))
                time.sleep(0.1)
                mock_terminal_session.resize.assert_called_with(40, 120)

    async def test_session_survives_idle_period(
        self,
        user_and_token: tuple[User, str],
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_terminal_session: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Sessiya idle davrda ham uzilmasligi kerak."""
        _, token = user_and_token
        app, patches = self._setup_ws_test(
            async_session_factory,
            mock_terminal_session,
            monkeypatch,
        )

        from starlette.testclient import TestClient

        with patches[0], patches[1], patches[2], TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/terminal?token={token}") as ws:
                ws.receive_json()  # status
                ws.receive_json()  # ready
                ws.receive_bytes()  # prompt

                time.sleep(1.0)

                ws.send_bytes(b"w")
                echo = ws.receive_bytes()
                assert echo == b"w"

    async def test_enter_command_returns_output(
        self,
        user_and_token: tuple[User, str],
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_terminal_session: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Enter bosilganda buyruq natijasi qaytishi kerak."""
        _, token = user_and_token
        app, patches = self._setup_ws_test(
            async_session_factory,
            mock_terminal_session,
            monkeypatch,
        )

        from starlette.testclient import TestClient

        with patches[0], patches[1], patches[2], TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/terminal?token={token}") as ws:
                ws.receive_json()  # status
                ws.receive_json()  # ready
                ws.receive_bytes()  # prompt

                ws.send_bytes(b"\r")
                echo1 = ws.receive_bytes()
                assert echo1 == b"\r"

                output = ws.receive_bytes()
                assert b"aisu@aisu:~$" in output

    async def test_multiple_rapid_inputs(
        self,
        user_and_token: tuple[User, str],
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_terminal_session: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Tez ketma-ket input da ham barcha data kelishi kerak."""
        _, token = user_and_token
        app, patches = self._setup_ws_test(
            async_session_factory,
            mock_terminal_session,
            monkeypatch,
        )

        from starlette.testclient import TestClient

        with patches[0], patches[1], patches[2], TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/terminal?token={token}") as ws:
                ws.receive_json()  # status
                ws.receive_json()  # ready
                ws.receive_bytes()  # prompt

                for ch in b"helloworld":
                    ws.send_bytes(bytes([ch]))

                received = b""
                for _ in range(10):
                    received += ws.receive_bytes()
                assert received == b"helloworld"
