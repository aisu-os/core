import logging

import httpx

from aiso_core.config import settings

logger = logging.getLogger(__name__)

_ROUTES_PATH = "/config/apps/http/servers/srv0/routes"


class CaddyError(Exception):
    """Caddy Admin API xatoligi."""


class CaddyService:
    """Caddy Admin API client — dynamic route boshqaruvi.

    ``caddy_admin_url`` bo'sh bo'lsa barcha metodlar no-op.
    """

    def __init__(self) -> None:
        self._base_url = (
            settings.caddy_admin_url.rstrip("/") if settings.caddy_admin_url else ""
        )
        self._domain = settings.port_forward_domain

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    async def _ensure_server(self, client: httpx.AsyncClient) -> None:
        """HTTP server mavjud bo'lmasa yaratish (bo'sh Caddyfile uchun)."""
        resp = await client.get(f"{self._base_url}{_ROUTES_PATH}")
        if resp.status_code == 200:
            return

        logger.info("Caddy srv0 mavjud emas, yaratilmoqda")
        resp = await client.post(
            f"{self._base_url}/config/apps",
            json={
                "http": {
                    "servers": {
                        "srv0": {
                            "listen": [":80"],
                            "routes": [],
                        }
                    }
                }
            },
        )
        if resp.status_code not in (200, 201):
            raise CaddyError(f"Server yaratishda xato: {resp.status_code} {resp.text}")

    async def add_route(self, subdomain: str, upstream: str) -> None:
        """Caddy ga reverse proxy route qo'shish.

        Args:
            subdomain: masalan "my-app"
            upstream: masalan "172.20.0.10:3000"
        """
        if not self.enabled:
            logger.debug("Caddy disabled, skipping add_route for %s", subdomain)
            return

        route_config = {
            "@id": f"pf-{subdomain}",
            "match": [{"host": [f"{subdomain}.{self._domain}"]}],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": upstream}],
                    "headers": {
                        "request": {
                            "set": {
                                "X-Forwarded-Host": ["{http.request.host}"],
                                "X-Real-IP": ["{http.request.remote.host}"],
                                "X-AISU-Subdomain": [subdomain],
                            }
                        }
                    },
                }
            ],
            "terminal": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await self._ensure_server(client)

                # Avval mavjud route ni o'chirib tashlaymiz (idempotent)
                await client.delete(f"{self._base_url}/id/pf-{subdomain}")

                # Route qo'shamiz
                resp = await client.post(
                    f"{self._base_url}{_ROUTES_PATH}",
                    json=route_config,
                )
        except httpx.HTTPError as exc:
            raise CaddyError(f"Caddy ulanish xatosi: {exc}") from exc

        if resp.status_code not in (200, 201):
            raise CaddyError(
                f"Route qo'shishda xato: {resp.status_code} {resp.text}"
            )

        logger.info(
            "Caddy route qo'shildi: %s.%s -> %s", subdomain, self._domain, upstream
        )

    async def remove_route(self, subdomain: str) -> None:
        """Caddy dan route o'chirish (@id bo'yicha)."""
        if not self.enabled:
            logger.debug("Caddy disabled, skipping remove_route for %s", subdomain)
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"{self._base_url}/id/pf-{subdomain}",
                )
        except httpx.HTTPError as exc:
            raise CaddyError(f"Caddy ulanish xatosi: {exc}") from exc

        # 404 — route allaqachon yo'q, muammo emas
        if resp.status_code not in (200, 404):
            raise CaddyError(
                f"Route o'chirishda xato: {resp.status_code} {resp.text}"
            )

        logger.info("Caddy route o'chirildi: pf-%s", subdomain)

    async def sync_routes(
        self, forwards: list[dict[str, str]]
    ) -> None:
        """Startup da barcha active forwardlarni Caddy ga yuklash.

        Args:
            forwards: [{"subdomain": "...", "upstream": "..."}]
        """
        if not self.enabled:
            logger.info("Caddy disabled, route sync o'tkazib yuborildi")
            return

        logger.info("%d ta route Caddy ga sync qilinmoqda", len(forwards))
        for fwd in forwards:
            try:
                await self.add_route(fwd["subdomain"], fwd["upstream"])
            except CaddyError:
                logger.warning(
                    "Route sync xatosi: %s", fwd["subdomain"], exc_info=True
                )
