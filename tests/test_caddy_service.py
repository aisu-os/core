"""CaddyService unit tests.

No real connection to Caddy Admin API — httpx is mocked.
"""

import pytest
from unittest.mock import AsyncMock, patch

from aiso_core.config import settings
from aiso_core.services.caddy_service import CaddyError, CaddyService


class TestCaddyServiceDisabled:
    """All methods are no-op when caddy_admin_url is empty."""

    @pytest.fixture(autouse=True)
    def _disable_caddy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "caddy_admin_url", "")

    def test_enabled_is_false(self) -> None:
        assert CaddyService().enabled is False

    async def test_add_route_noop(self) -> None:
        caddy = CaddyService()
        # Does not raise an error, does nothing
        await caddy.add_route("test", "172.20.0.2:3000")

    async def test_remove_route_noop(self) -> None:
        caddy = CaddyService()
        await caddy.remove_route("test")

    async def test_sync_routes_noop(self) -> None:
        caddy = CaddyService()
        await caddy.sync_routes([{"subdomain": "a", "upstream": "1.2.3.4:80"}])


class TestCaddyServiceEnabled:
    """When caddy_admin_url is set — with httpx mock (HTTP mode)."""

    @pytest.fixture(autouse=True)
    def _enable_caddy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "caddy_admin_url", "http://caddy:2019")
        monkeypatch.setattr(settings, "port_forward_domain", "t.localhost")
        monkeypatch.setattr(settings, "port_forward_scheme", "http")
        monkeypatch.setattr(settings, "caddy_tls_cert", "")
        monkeypatch.setattr(settings, "caddy_tls_key", "")

    def test_enabled_is_true(self) -> None:
        assert CaddyService().enabled is True

    async def test_add_route_success(self) -> None:
        mock_client = AsyncMock()
        # _ensure_server: GET routes → 200 (server exists)
        mock_client.get.return_value = AsyncMock(status_code=200)
        # DELETE old route → 200
        mock_client.delete.return_value = AsyncMock(status_code=200)
        # POST new route → 200
        mock_client.post.return_value = AsyncMock(status_code=200)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.add_route("myapp", "172.20.0.5:3000")

        # Verify POST was called
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/routes" in call_args[0][0]
        route_json = call_args[1]["json"]
        assert route_json["@id"] == "pf-myapp"
        assert route_json["match"][0]["host"] == ["myapp.t.localhost"]
        assert route_json["handle"][0]["upstreams"][0]["dial"] == "172.20.0.5:3000"

    async def test_add_route_creates_server_if_missing(self) -> None:
        mock_client = AsyncMock()
        # _ensure_server: GET routes → 404 (server does not exist)
        mock_client.get.return_value = AsyncMock(status_code=404)
        # _ensure_server: PUT server → 200 (server created)
        mock_client.put.return_value = AsyncMock(status_code=200)
        # add_route: POST route → 200
        mock_client.post.return_value = AsyncMock(status_code=200)
        mock_client.delete.return_value = AsyncMock(status_code=404)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.add_route("myapp", "172.20.0.5:3000")

        # PUT was called to create server
        mock_client.put.assert_called_once()
        put_url = mock_client.put.call_args[0][0]
        assert "/servers/pf-srv" in put_url
        server_json = mock_client.put.call_args[1]["json"]
        assert server_json["listen"] == [":80"]
        assert "tls_connection_policies" not in server_json

        # POST was called to add route
        mock_client.post.assert_called_once()

    async def test_add_route_failure_raises(self) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = AsyncMock(status_code=200)
        mock_client.delete.return_value = AsyncMock(status_code=200)
        mock_client.post.return_value = AsyncMock(status_code=500, text="internal error")

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            with pytest.raises(CaddyError, match="Failed to add route"):
                await caddy.add_route("fail", "1.2.3.4:80")

    async def test_remove_route_success(self) -> None:
        mock_client = AsyncMock()
        mock_client.delete.return_value = AsyncMock(status_code=200)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.remove_route("myapp")

        mock_client.delete.assert_called_once()
        assert "pf-myapp" in mock_client.delete.call_args[0][0]

    async def test_remove_route_404_is_ok(self) -> None:
        """Does not raise an error if the route already does not exist."""
        mock_client = AsyncMock()
        mock_client.delete.return_value = AsyncMock(status_code=404)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.remove_route("nonexistent")  # Does not raise an error

    async def test_remove_route_500_raises(self) -> None:
        mock_client = AsyncMock()
        mock_client.delete.return_value = AsyncMock(status_code=500, text="server error")

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            with pytest.raises(CaddyError, match="Failed to remove route"):
                await caddy.remove_route("broken")

    async def test_sync_routes_calls_add_for_each(self) -> None:
        caddy = CaddyService()
        caddy.add_route = AsyncMock()  # type: ignore[method-assign]

        forwards = [
            {"subdomain": "app1", "upstream": "172.20.0.2:3000"},
            {"subdomain": "app2", "upstream": "172.20.0.3:8080"},
        ]
        await caddy.sync_routes(forwards)

        assert caddy.add_route.call_count == 2

    async def test_sync_routes_continues_on_error(self) -> None:
        """If one route fails, continues with the remaining ones."""
        caddy = CaddyService()
        caddy.add_route = AsyncMock(  # type: ignore[method-assign]
            side_effect=[CaddyError("fail"), None],
        )

        forwards = [
            {"subdomain": "broken", "upstream": "1.2.3.4:80"},
            {"subdomain": "ok", "upstream": "5.6.7.8:80"},
        ]
        await caddy.sync_routes(forwards)

        assert caddy.add_route.call_count == 2


class TestCaddyServiceTLS:
    """When TLS is configured (production mode)."""

    @pytest.fixture(autouse=True)
    def _enable_caddy_tls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "caddy_admin_url", "http://caddy:2019")
        monkeypatch.setattr(settings, "port_forward_domain", "t.aisu.run")
        monkeypatch.setattr(settings, "port_forward_scheme", "https")
        monkeypatch.setattr(settings, "caddy_tls_cert", "/etc/caddy/certs/origin.pem")
        monkeypatch.setattr(settings, "caddy_tls_key", "/etc/caddy/certs/origin-key.pem")

    async def test_creates_server_with_tls(self) -> None:
        mock_client = AsyncMock()
        # _ensure_server: GET routes → 404
        get_routes_resp = AsyncMock(status_code=404)
        # _ensure_tls_loaded: GET load_files → 404 (not loaded yet)
        get_tls_resp = AsyncMock(status_code=404)
        mock_client.get.side_effect = [get_routes_resp, get_tls_resp]
        # _ensure_tls_loaded: POST load_files → 200
        # add_route: POST route → 200
        mock_client.post.side_effect = [
            AsyncMock(status_code=200),  # TLS cert load
            AsyncMock(status_code=200),  # add route
        ]
        # _ensure_server: PUT server → 200
        mock_client.put.return_value = AsyncMock(status_code=200)
        mock_client.delete.return_value = AsyncMock(status_code=404)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.add_route("myapp", "172.20.0.5:3000")

        # Server created with :443 and TLS
        mock_client.put.assert_called_once()
        server_json = mock_client.put.call_args[1]["json"]
        assert server_json["listen"] == [":443"]
        assert "tls_connection_policies" in server_json

    async def test_route_uses_tls_domain(self) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = AsyncMock(status_code=200)
        mock_client.delete.return_value = AsyncMock(status_code=200)
        mock_client.post.return_value = AsyncMock(status_code=200)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.add_route("myapp", "172.20.0.5:3000")

        route_json = mock_client.post.call_args[1]["json"]
        assert route_json["match"][0]["host"] == ["myapp.t.aisu.run"]
