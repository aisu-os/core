from __future__ import annotations

import asyncio
import logging
import socket
import uuid

from aiso_core.config import settings

logger = logging.getLogger(__name__)

# Config to hide screen
_SCREENRC_PATH = "/tmp/.aisu_screenrc"
_SCREENRC_CONTENT = (
    'escape ""\n'
    "vbell off\n"
    "autodetach on\n"
    "startup_message off\n"
    "defscrollback 10000\n"
    "term xterm-256color\n"
    "shell /bin/bash\n"
    "defshell /bin/bash\n"
    # Disable alternate screen buffer — so xterm.js scrollback works
    "termcapinfo xterm* ti@:te@\n"
)


def _get_docker_client():  # noqa: ANN202
    from aiso_core.services.docker_client import get_docker_client

    return get_docker_client()


def _extract_socket(sock_adapter: object) -> socket.socket:
    """Get raw socket from docker-py exec_start(socket=True).

    The returned object type varies depending on docker-py version:
    - SocketIO wrapper → ._sock attribute
    - Direct socket
    """
    # docker-py SocketIO wrapper
    if hasattr(sock_adapter, "_sock"):
        raw = sock_adapter._sock  # noqa: SLF001
        if isinstance(raw, socket.socket):
            return raw
        if hasattr(raw, "fileno"):
            return raw

    # urllib3 response wrapper
    if hasattr(sock_adapter, "fileno"):
        return sock_adapter  # type: ignore[return-value]

    raise RuntimeError(f"Failed to get Docker socket: {type(sock_adapter)}")


class TerminalSession:
    """A single terminal session = docker exec + GNU screen.

    The screen session runs persistently inside the container.
    Even if WebSocket disconnects, the screen session is preserved.
    On reconnection, it attaches to the existing session.

    Why screen instead of tmux: tmux cannot run inside tmux
    (nested tmux issue). screen and tmux don't interfere with each other,
    so if the backend uses screen, the user can freely use tmux.
    """

    def __init__(self, container_name: str, session_id: str | None = None) -> None:
        self.container_name = container_name
        self.session_id = session_id or str(uuid.uuid4())
        # screen session name
        self._screen_session = f"term_{self.session_id[:8]}"
        self._exec_id: str | None = None
        self._raw_socket: socket.socket | None = None
        self._socket_adapter: object | None = None
        self._closed = False

    async def _check_existing_session(self, client: object) -> bool:
        """Check for an existing screen session in the container."""
        try:
            check_result = await asyncio.to_thread(
                client.api.exec_create,  # type: ignore[union-attr]
                self.container_name,
                cmd=["screen", "-ls"],
                stdin=False,
                tty=False,
                user="aisu",
            )
            output = await asyncio.to_thread(
                client.api.exec_start,  # type: ignore[union-attr]
                check_result["Id"],
            )
            output_str = output.decode() if isinstance(output, bytes) else str(output)
            return self._screen_session in output_str
        except Exception:
            logger.debug("Error checking screen -ls", exc_info=True)
            return False

    async def start(self) -> None:
        """Create a screen session or attach to an existing one via exec."""
        client = _get_docker_client()

        # 1. Create screenrc (always — idempotent)
        screenrc_result = await asyncio.to_thread(
            client.api.exec_create,
            self.container_name,
            cmd=[
                "bash",
                "-c",
                f"cat > {_SCREENRC_PATH} << 'SCREENRC'\n{_SCREENRC_CONTENT}SCREENRC",
            ],
            stdin=False,
            tty=False,
            user="aisu",
        )
        await asyncio.to_thread(
            client.api.exec_start,
            screenrc_result["Id"],
        )

        # 2. Check for existing screen session
        session_exists = await self._check_existing_session(client)

        if not session_exists:
            # Create new screen session (detached, with bash shell)
            create_result = await asyncio.to_thread(
                client.api.exec_create,
                self.container_name,
                cmd=[
                    "screen",
                    "-c",
                    _SCREENRC_PATH,
                    "-dmS",
                    self._screen_session,
                    "bash",
                ],
                stdin=False,
                tty=False,
                user="aisu",
                environment={"TERM": "xterm-256color"},
            )
            create_output = await asyncio.to_thread(
                client.api.exec_start,
                create_result["Id"],
            )
            # Verify screen was created
            inspect = await asyncio.to_thread(
                client.api.exec_inspect,
                create_result["Id"],
            )
            if inspect.get("ExitCode", 1) != 0:
                raise RuntimeError(
                    f"Failed to create screen session: exit={inspect.get('ExitCode')}, "
                    f"output={create_output}"
                )
            logger.debug("New screen session created: %s", self._screen_session)
        else:
            logger.debug("Attaching to existing screen session: %s", self._screen_session)

        # 3. Attach to screen session (interactive exec + socket)
        # -d -r: first detaches any existing attachment (if any),
        # then reattaches. This works even when the previous exec
        # wasn't fully closed (e.g., WebSocket disconnection).
        exec_data = await asyncio.to_thread(
            client.api.exec_create,
            self.container_name,
            cmd=[
                "screen",
                "-c",
                _SCREENRC_PATH,
                "-d",
                "-r",
                self._screen_session,
            ],
            stdin=True,
            tty=True,
            user="aisu",
            environment={"TERM": "xterm-256color"},
        )
        self._exec_id = exec_data["Id"]

        self._socket_adapter = await asyncio.to_thread(
            client.api.exec_start,
            self._exec_id,
            socket=True,
            tty=True,
        )
        self._raw_socket = _extract_socket(self._socket_adapter)
        # Remove Docker API default timeout
        self._raw_socket.settimeout(None)

    async def read(self, size: int = 4096) -> bytes:
        """Read data from the container (non-blocking via thread pool)."""
        if self._raw_socket is None or self._closed:
            return b""

        try:
            data: bytes = await asyncio.to_thread(self._raw_socket.recv, size)
            return data
        except OSError:
            if self._closed:
                return b""
            raise

    async def write(self, data: bytes) -> None:
        """Write data to the container."""
        if self._raw_socket is None or self._closed:
            return

        await asyncio.to_thread(self._raw_socket.sendall, data)

    async def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal.

        screen automatically adapts to the PTY size of the attachment,
        so only exec resize is needed.
        """
        if self._exec_id is None:
            return

        client = _get_docker_client()
        await asyncio.to_thread(
            client.api.exec_resize,
            self._exec_id,
            height=rows,
            width=cols,
        )

    async def close(self) -> None:
        """Close socket and resources.

        The screen session is not closed — it is preserved for the next connection.
        We only close the attach exec socket.
        """
        if self._closed:
            return
        self._closed = True

        if self._raw_socket is not None:
            try:
                await asyncio.to_thread(self._raw_socket.close)
            except Exception:
                logger.debug("Error closing socket", exc_info=True)
            self._raw_socket = None
            self._socket_adapter = None

    async def kill_screen_session(self) -> None:
        """Completely kill the screen session (when the window is closed)."""
        try:
            client = _get_docker_client()
            exec_id = await asyncio.to_thread(
                client.api.exec_create,
                self.container_name,
                cmd=["screen", "-S", self._screen_session, "-X", "quit"],
                user="aisu",
            )
            await asyncio.to_thread(client.api.exec_start, exec_id)
        except Exception:
            logger.debug("Error killing screen session", exc_info=True)

    @property
    def is_closed(self) -> bool:
        return self._closed
