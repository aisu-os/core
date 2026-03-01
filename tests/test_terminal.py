"""Terminal WebSocket endpoint and TerminalSession tests.

Works with a mock Docker socket — no real Docker required.
Tests the GNU screen approach.
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
    """Mock socket — simulates recv() and sendall()."""
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
    """Mock Docker client — simulates the screen stream."""
    client = MagicMock()

    # exec_create returns a new ID each time
    # 4 execs: screenrc setup + screen -ls check + screen create + screen attach
    exec_ids = iter(
        [
            "exec_screenrc_setup",
            "exec_screen_check_001",
            "exec_screen_create_123",
            "exec_screen_attach_456",
        ]
    )
    client.api.exec_create.side_effect = lambda *a, **kw: {"Id": next(exec_ids)}

    # exec_start results:
    # 1. screenrc setup -> bytes output
    # 2. screen -ls check
    # 3. screen -dmS (create) -> bytes output
    # 4. screen -d -r (attach) -> socket wrapper
    socket_wrapper = MagicMock()
    socket_wrapper._sock = mock_socket

    start_results = iter([b"", b"No Sockets found.", b"", socket_wrapper])
    client.api.exec_start.side_effect = lambda *a, **kw: next(start_results)

    # exec_inspect (screen create result)
    client.api.exec_inspect.return_value = {"ExitCode": 0, "Running": False}

    client.api.exec_resize.return_value = None

    container_mock = MagicMock()
    container_mock.status = "running"
    client.containers.get.return_value = container_mock

    return client


# ── TerminalSession tests ──


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

            # exec_create should be called 4 times
            # (screenrc + screen -ls + screen create + screen attach)
            assert mock_docker_client.api.exec_create.call_count == 4

            # First — screenrc setup (bash -c ...)
            first_call = mock_docker_client.api.exec_create.call_args_list[0]
            first_cmd = first_call[1]["cmd"]
            assert first_cmd[0] == "bash"
            assert first_cmd[1] == "-c"

            # Second — screen -ls (check for existing session)
            second_call = mock_docker_client.api.exec_create.call_args_list[1]
            second_cmd = second_call[1]["cmd"]
            assert second_cmd[0] == "screen"
            assert "-ls" in second_cmd

            # Third — screen -dmS (create session)
            third_call = mock_docker_client.api.exec_create.call_args_list[2]
            third_cmd = third_call[1]["cmd"]
            assert third_cmd[0] == "screen"
            assert "-dmS" in third_cmd

            # Fourth — screen -d -r (attach)
            fourth_call = mock_docker_client.api.exec_create.call_args_list[3]
            fourth_cmd = fourth_call[1]["cmd"]
            assert fourth_cmd[0] == "screen"
            assert "-d" in fourth_cmd
            assert "-r" in fourth_cmd

    async def test_start_attaches_existing_session_without_creating_new_one(
        self,
        mock_socket: MagicMock,
    ) -> None:
        client = MagicMock()
        socket_wrapper = MagicMock()
        socket_wrapper._sock = mock_socket
        session = TerminalSession("aisu_test", session_id="my-session-01")

        client.api.exec_create.side_effect = [
            {"Id": "exec_screenrc_setup"},
            {"Id": "exec_screen_check_001"},
            {"Id": "exec_screen_attach_456"},
        ]
        client.api.exec_start.side_effect = [
            b"",
            f"There is a screen on:\n\t{session._screen_session}".encode(),
            socket_wrapper,
        ]

        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=client,
        ):
            await session.start()

        called_cmds = [call[1]["cmd"] for call in client.api.exec_create.call_args_list]
        assert len(called_cmds) == 3
        assert not any("-dmS" in cmd for cmd in called_cmds)
        assert "-d" in called_cmds[2]
        assert "-r" in called_cmds[2]

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
        mock_docker_client.api.exec_start.side_effect = [
            b"",
            b"No Sockets found.",
            b"",
            socket_wrapper,
        ]
        mock_docker_client.api.exec_create.side_effect = [
            {"Id": "e1"},
            {"Id": "e2"},
            {"Id": "e3"},
            {"Id": "e4"},
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
        mock_docker_client.api.exec_start.side_effect = [
            b"",
            b"No Sockets found.",
            b"",
            socket_wrapper,
        ]
        mock_docker_client.api.exec_create.side_effect = [
            {"Id": "e1"},
            {"Id": "e2"},
            {"Id": "e3"},
            {"Id": "e4"},
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
        """Should raise RuntimeError if screen cannot be created."""
        mock_docker_client.api.exec_inspect.return_value = {"ExitCode": 1}
        # screenrc setup succeeds, but screen create fails
        mock_docker_client.api.exec_create.side_effect = [
            {"Id": "e_screenrc"},
            {"Id": "e_check"},
            {"Id": "e_create"},
        ]
        mock_docker_client.api.exec_start.side_effect = [b"", b"No Sockets found.", b"no screen running"]

        with patch(
            "aiso_core.services.terminal_service._get_docker_client",
            return_value=mock_docker_client,
        ):
            session = TerminalSession("aisu_test")
            with pytest.raises(RuntimeError, match="Failed to create screen session"):
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
        with pytest.raises(RuntimeError, match="Failed to get Docker socket"):
            _extract_socket(wrapper)

    def test_nested_sock_with_fileno(self) -> None:
        """Nested wrapper — _sock.fileno() exists but is not socket.socket."""
        inner = MagicMock()
        inner.fileno.return_value = 7
        del inner.family
        wrapper = MagicMock()
        wrapper._sock = inner
        result = _extract_socket(wrapper)
        assert result is inner


# ── WebSocket endpoint tests ──


class TestTerminalWebSocket:
    """Terminal WebSocket endpoint integration tests."""

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
        """Stable mock TerminalSession."""
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
        """Common setup for WebSocket tests — monkeypatch + mock."""
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
        """Full session: connect → ready → input → output → disconnect."""
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

    async def test_ws_passes_session_id_to_terminal_session(
        self,
        user_and_token: tuple[User, str],
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_terminal_session: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, token = user_and_token
        from starlette.testclient import TestClient

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

        with (
            patch(
                "aiso_core.api.v1.terminal.ContainerService",
                return_value=mock_container_instance,
            ),
            patch(
                "aiso_core.api.v1.terminal.TerminalSession",
                return_value=mock_terminal_session,
            ) as terminal_session_cls,
            TestClient(app) as tc,
        ):
            with tc.websocket_connect(f"/ws/terminal?token={token}&session_id=persist-001") as ws:
                ws.receive_json()  # status
                ws.receive_json()  # ready

            expected_container_name = f"aisu_{user_and_token[0].id}"
            terminal_session_cls.assert_called_once_with(
                expected_container_name,
                session_id="persist-001",
            )

    async def test_session_survives_idle_period(
        self,
        user_and_token: tuple[User, str],
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_terminal_session: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Session should not disconnect during idle period."""
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
        """Should return command output when Enter is pressed."""
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
        """All data should be received even with rapid sequential input."""
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
