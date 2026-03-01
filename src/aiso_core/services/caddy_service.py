import logging

import httpx

from aiso_core.config import settings

logger = logging.getLogger(__name__)

_ROUTES_PATH = "/config/apps/http/servers/srv0/routes"


class CaddyError(Exception):
    """Caddy Admin API error."""


class CaddyService:
    """Caddy Admin API client — dynamic route management.

    All methods are no-op if ``caddy_admin_url`` is empty.
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
        """Create HTTP server if it doesn't exist (for empty Caddyfile)."""
        resp = await client.get(f"{self._base_url}{_ROUTES_PATH}")
        if resp.status_code == 200:
            return

        logger.info("Caddy srv0 not found, creating")
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
            raise CaddyError(f"Failed to create server: {resp.status_code} {resp.text}")

    async def add_route(self, subdomain: str, upstream: str) -> None:
        """Add a reverse proxy route to Caddy.

        Args:
            subdomain: e.g. "my-app"
            upstream: e.g. "172.20.0.10:3000"
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

                # First remove existing route (idempotent)
                await client.delete(f"{self._base_url}/id/pf-{subdomain}")

                # Add route
                resp = await client.post(
                    f"{self._base_url}{_ROUTES_PATH}",
                    json=route_config,
                )
        except httpx.HTTPError as exc:
            raise CaddyError(f"Caddy connection error: {exc}") from exc

        if resp.status_code not in (200, 201):
            raise CaddyError(
                f"Failed to add route: {resp.status_code} {resp.text}"
            )

        logger.info(
            "Caddy route added: %s.%s -> %s", subdomain, self._domain, upstream
        )

    async def remove_route(self, subdomain: str) -> None:
        """Remove a route from Caddy (by @id)."""
        if not self.enabled:
            logger.debug("Caddy disabled, skipping remove_route for %s", subdomain)
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"{self._base_url}/id/pf-{subdomain}",
                )
        except httpx.HTTPError as exc:
            raise CaddyError(f"Caddy connection error: {exc}") from exc

        # 404 — route already gone, not a problem
        if resp.status_code not in (200, 404):
            raise CaddyError(
                f"Failed to remove route: {resp.status_code} {resp.text}"
            )

        logger.info("Caddy route removed: pf-%s", subdomain)

    async def sync_routes(
        self, forwards: list[dict[str, str]]
    ) -> None:
        """Load all active forwards into Caddy at startup.

        Args:
            forwards: [{"subdomain": "...", "upstream": "..."}]
        """
        if not self.enabled:
            logger.info("Caddy disabled, skipping route sync")
            return

        logger.info("Syncing %d routes to Caddy", len(forwards))
        for fwd in forwards:
            try:
                await self.add_route(fwd["subdomain"], fwd["upstream"])
            except CaddyError:
                logger.warning(
                    "Route sync error: %s", fwd["subdomain"], exc_info=True
                )
