"""CaddyService unit testlari.

Caddy Admin API ga haqiqiy ulanish yo'q — httpx mock qilinadi.
"""

import pytest
from unittest.mock import AsyncMock, patch

from aiso_core.config import settings
from aiso_core.services.caddy_service import CaddyError, CaddyService


class TestCaddyServiceDisabled:
    """caddy_admin_url bo'sh bo'lganda barcha metodlar no-op."""

    @pytest.fixture(autouse=True)
    def _disable_caddy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "caddy_admin_url", "")

    def test_enabled_is_false(self) -> None:
        assert CaddyService().enabled is False

    async def test_add_route_noop(self) -> None:
        caddy = CaddyService()
        # Xato bermaydi, hech narsa qilmaydi
        await caddy.add_route("test", "172.20.0.2:3000")

    async def test_remove_route_noop(self) -> None:
        caddy = CaddyService()
        await caddy.remove_route("test")

    async def test_sync_routes_noop(self) -> None:
        caddy = CaddyService()
        await caddy.sync_routes([{"subdomain": "a", "upstream": "1.2.3.4:80"}])


class TestCaddyServiceEnabled:
    """caddy_admin_url mavjud bo'lganda — httpx mock bilan."""

    @pytest.fixture(autouse=True)
    def _enable_caddy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "caddy_admin_url", "http://caddy:2019")
        monkeypatch.setattr(settings, "port_forward_domain", "t.localhost")

    def test_enabled_is_true(self) -> None:
        assert CaddyService().enabled is True

    async def test_add_route_success(self) -> None:
        mock_client = AsyncMock()
        # _ensure_server: GET routes → 200 (server mavjud)
        mock_client.get.return_value = AsyncMock(status_code=200)
        # DELETE eski route → 200
        mock_client.delete.return_value = AsyncMock(status_code=200)
        # POST yangi route → 200
        mock_client.post.return_value = AsyncMock(status_code=200)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.add_route("myapp", "172.20.0.5:3000")

        # POST chaqirilganini tekshirish
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/routes" in call_args[0][0]
        route_json = call_args[1]["json"]
        assert route_json["@id"] == "pf-myapp"
        assert route_json["match"][0]["host"] == ["myapp.t.localhost"]
        assert route_json["handle"][0]["upstreams"][0]["dial"] == "172.20.0.5:3000"

    async def test_add_route_creates_server_if_missing(self) -> None:
        mock_client = AsyncMock()
        # _ensure_server: GET routes → 404 (server yo'q)
        mock_client.get.return_value = AsyncMock(status_code=404)
        # _ensure_server: POST apps → 200 (server yaratildi)
        mock_client.post.side_effect = [
            AsyncMock(status_code=200),  # _ensure_server POST
            AsyncMock(status_code=200),  # add_route POST
        ]
        mock_client.delete.return_value = AsyncMock(status_code=404)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.add_route("myapp", "172.20.0.5:3000")

        # POST ikki marta chaqirildi: 1) server yaratish, 2) route qo'shish
        assert mock_client.post.call_count == 2

    async def test_add_route_failure_raises(self) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = AsyncMock(status_code=200)
        mock_client.delete.return_value = AsyncMock(status_code=200)
        mock_client.post.return_value = AsyncMock(status_code=500, text="internal error")

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            with pytest.raises(CaddyError, match="Route qo'shishda xato"):
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
        """Route allaqachon yo'q bo'lsa xato bermaydi."""
        mock_client = AsyncMock()
        mock_client.delete.return_value = AsyncMock(status_code=404)

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            await caddy.remove_route("nonexistent")  # Xato bermaydi

    async def test_remove_route_500_raises(self) -> None:
        mock_client = AsyncMock()
        mock_client.delete.return_value = AsyncMock(status_code=500, text="server error")

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiso_core.services.caddy_service.httpx.AsyncClient", return_value=mock_client):
            caddy = CaddyService()
            with pytest.raises(CaddyError, match="Route o'chirishda xato"):
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
        """Bitta route xato bo'lsa, qolganlarni davom ettiradi."""
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
