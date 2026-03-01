import logging

import httpx

from aiso_core.config import settings

logger = logging.getLogger(__name__)

_SERVER_NAME = "pf-srv"
_ROUTES_PATH = f"/config/apps/http/servers/{_SERVER_NAME}/routes"


class CaddyError(Exception):
    """Caddy Admin API error."""


class CaddyService:
    """Caddy Admin API client — dynamic route management.

    All methods are no-op if ``caddy_admin_url`` is empty.

    In production (scheme=https, cert/key configured), the dynamically
    created ``pf-srv`` listens on :443 with TLS using Cloudflare Origin
    Certificate loaded via ``tls.certificates.load_files``.
    """

    def __init__(self) -> None:
        self._base_url = (
            settings.caddy_admin_url.rstrip("/") if settings.caddy_admin_url else ""
        )
        self._domain = settings.port_forward_domain
        self._scheme = settings.port_forward_scheme
        self._tls_cert = settings.caddy_tls_cert
        self._tls_key = settings.caddy_tls_key
        self._api_domain = settings.caddy_api_domain
        self._api_upstream = settings.caddy_api_upstream

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    @property
    def _use_tls(self) -> bool:
        return self._scheme == "https" and bool(self._tls_cert) and bool(self._tls_key)

    async def _ensure_tls_loaded(self, client: httpx.AsyncClient) -> None:
        """Load Origin Certificate into Caddy if not already present."""
        resp = await client.get(
            f"{self._base_url}/config/apps/tls/certificates/load_files"
        )
        if resp.status_code == 200 and resp.json():
            return

        logger.info("Loading TLS origin certificate for port-forward server")
        resp = await client.post(
            f"{self._base_url}/config/apps/tls/certificates/load_files",
            json=[
                {
                    "certificate": self._tls_cert,
                    "key": self._tls_key,
                }
            ],
        )
        if resp.status_code not in (200, 201):
            logger.warning(
                "Failed to load TLS cert: %s %s", resp.status_code, resp.text
            )

    async def _ensure_server(self, client: httpx.AsyncClient) -> None:
        """Create HTTP/HTTPS server if it doesn't exist.

        Uses PUT on the specific server path to avoid overwriting
        other servers created by Caddyfile (e.g. api.aisu.run).
        """
        resp = await client.get(f"{self._base_url}{_ROUTES_PATH}")
        if resp.status_code == 200:
            return

        logger.info("Caddy %s not found, creating", _SERVER_NAME)

        listen_port = ":443" if self._use_tls else ":80"
        server_config: dict = {
            "listen": [listen_port],
            "routes": [],
        }

        if self._use_tls:
            server_config["tls_connection_policies"] = [{}]
            await self._ensure_tls_loaded(client)

        # PUT only pf-srv — does not affect other servers from Caddyfile
        resp = await client.put(
            f"{self._base_url}/config/apps/http/servers/{_SERVER_NAME}",
            json=server_config,
        )
        if resp.status_code not in (200, 201):
            raise CaddyError(f"Failed to create server: {resp.status_code} {resp.text}")

        logger.info("Caddy %s created (listen=%s, tls=%s)", _SERVER_NAME, listen_port, self._use_tls)

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

    async def ensure_api_route(self) -> None:
        """Add API reverse proxy route if ``caddy_api_domain`` is set."""
        if not self.enabled or not self._api_domain:
            return

        route_config = {
            "@id": "api-proxy",
            "match": [{"host": [self._api_domain]}],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": self._api_upstream}],
                }
            ],
            "terminal": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await self._ensure_server(client)
                await client.delete(f"{self._base_url}/id/api-proxy")
                resp = await client.post(
                    f"{self._base_url}{_ROUTES_PATH}",
                    json=route_config,
                )
        except httpx.HTTPError as exc:
            raise CaddyError(f"Caddy connection error: {exc}") from exc

        if resp.status_code not in (200, 201):
            raise CaddyError(
                f"Failed to add API route: {resp.status_code} {resp.text}"
            )

        logger.info("Caddy API route added: %s -> %s", self._api_domain, self._api_upstream)

    async def sync_routes(
        self, forwards: list[dict[str, str]]
    ) -> None:
        """Load all active forwards into Caddy at startup.

        Also ensures the API reverse proxy route exists if configured.

        Args:
            forwards: [{"subdomain": "...", "upstream": "..."}]
        """
        if not self.enabled:
            logger.info("Caddy disabled, skipping route sync")
            return

        try:
            await self.ensure_api_route()
        except CaddyError:
            logger.warning("API route sync error", exc_info=True)

        logger.info("Syncing %d port-forward routes to Caddy", len(forwards))
        for fwd in forwards:
            try:
                await self.add_route(fwd["subdomain"], fwd["upstream"])
            except CaddyError:
                logger.warning(
                    "Route sync error: %s", fwd["subdomain"], exc_info=True
                )
