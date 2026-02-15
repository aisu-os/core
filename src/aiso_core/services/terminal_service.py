from __future__ import annotations

import asyncio
import logging
import socket
import uuid

from aiso_core.config import settings

logger = logging.getLogger(__name__)

# screen ni yashirin qilish uchun config
_SCREENRC_PATH = "/tmp/.aisu_screenrc"
_SCREENRC_CONTENT = (
    'escape ""\n'
    "vbell off\n"
    "autodetach on\n"
    "startup_message off\n"
    "defscrollback 10000\n"
    "term xterm-256color\n"
)


def _get_docker_client():  # noqa: ANN202
    import docker

    return docker.DockerClient(base_url=settings.docker_base_url)


def _extract_socket(sock_adapter: object) -> socket.socket:
    """docker-py exec_start(socket=True) dan raw socket olish.

    docker-py versiyasiga qarab qaytariladigan obyekt turlicha:
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

    raise RuntimeError(f"Docker socket olishda xatolik: {type(sock_adapter)}")


class TerminalSession:
    """Bitta terminal sessiya = docker exec + GNU screen.

    screen sessiya container ichida doimiy ishlaydi.
    WebSocket uzilsa ham screen sessiya saqlanadi.
    Qayta ulanishda mavjud sessiyaga attach bo'ladi.

    screen ishlatilishining sababi: tmux ichida tmux ishlatib bo'lmaydi
    (nested tmux muammosi). screen va tmux bir-biriga to'sqinlik qilmaydi,
    shuning uchun backend screen ishlatsa, user tmux ni erkin ishlata oladi.
    """

    def __init__(self, container_name: str, session_id: str | None = None) -> None:
        self.container_name = container_name
        self.session_id = session_id or str(uuid.uuid4())
        # screen session nomi
        self._screen_session = f"term_{self.session_id[:8]}"
        self._exec_id: str | None = None
        self._raw_socket: socket.socket | None = None
        self._socket_adapter: object | None = None
        self._closed = False

    async def start(self) -> None:
        """screen sessiya yaratib, unga exec orqali ulanadi."""
        client = _get_docker_client()

        # 1. screenrc yaratish (screen ni yashirin qilish uchun)
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

        # 2. screen sessiya yaratish (detached)
        create_result = await asyncio.to_thread(
            client.api.exec_create,
            self.container_name,
            cmd=[
                "screen",
                "-c",
                _SCREENRC_PATH,
                "-dmS",
                self._screen_session,
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
        # screen yaratilganini tekshirish
        inspect = await asyncio.to_thread(
            client.api.exec_inspect,
            create_result["Id"],
        )
        if inspect.get("ExitCode", 1) != 0:
            raise RuntimeError(
                f"screen session yaratib bo'lmadi: exit={inspect.get('ExitCode')}, "
                f"output={create_output}"
            )

        # 3. screen sessiyaga attach bo'lish (interactive exec + socket)
        exec_data = await asyncio.to_thread(
            client.api.exec_create,
            self.container_name,
            cmd=[
                "screen",
                "-c",
                _SCREENRC_PATH,
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
        # Docker API default timeout ni olib tashlash
        self._raw_socket.settimeout(None)

    async def read(self, size: int = 4096) -> bytes:
        """Container dan ma'lumot o'qish (thread pool orqali non-blocking)."""
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
        """Container ga ma'lumot yozish."""
        if self._raw_socket is None or self._closed:
            return

        await asyncio.to_thread(self._raw_socket.sendall, data)

    async def resize(self, rows: int, cols: int) -> None:
        """Terminal o'lchamini o'zgartirish.

        screen attach qilingan PTY o'lchamiga avtomatik moslashadi,
        shuning uchun faqat exec resize yetarli.
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
        """Socket va resurslarni yopish.

        screen sessiya yopilmaydi — keyingi ulanish uchun saqlanadi.
        Faqat attach exec socketni yopamiz.
        """
        if self._closed:
            return
        self._closed = True

        if self._raw_socket is not None:
            try:
                await asyncio.to_thread(self._raw_socket.close)
            except Exception:
                logger.debug("Socket yopishda xatolik", exc_info=True)
            self._raw_socket = None
            self._socket_adapter = None

    async def kill_screen_session(self) -> None:
        """screen sessiyani to'liq o'chirish (oyna yopilganda)."""
        try:
            client = _get_docker_client()
            await asyncio.to_thread(
                client.api.exec_create,
                self.container_name,
                cmd=["screen", "-S", self._screen_session, "-X", "quit"],
                user="aisu",
            )
        except Exception:
            logger.debug("screen kill-session xatolik", exc_info=True)

    @property
    def is_closed(self) -> bool:
        return self._closed
