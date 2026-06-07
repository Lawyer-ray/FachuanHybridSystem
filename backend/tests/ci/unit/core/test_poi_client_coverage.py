"""Coverage tests for core.services.poi_client."""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.poi_client import POIServiceClient, get_poi_client, _get_poi_url


class TestGetPoiUrl:
    def test_returns_url(self):
        url = _get_poi_url()
        assert isinstance(url, str)
        assert len(url) > 0

    def test_with_custom_settings(self):
        with patch("django.conf.settings") as mock_settings:
            mock_settings.POI_SERVICE_URL = "http://custom:9999"
            url = _get_poi_url()
            assert url == "http://custom:9999"


class TestPOIServiceClient:
    def _make(self):
        return POIServiceClient(base_url="http://test:8090", timeout=5.0)

    def test_init_defaults(self):
        client = POIServiceClient()
        assert client.base_url
        assert client.timeout == 30.0

    def test_init_custom(self):
        client = POIServiceClient(base_url="http://custom:9090/", timeout=10.0)
        assert client.base_url == "http://custom:9090"

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_post_request(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.content = b"docx_bytes"
        mock_instance = MagicMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        result = client._post("/test", {"key": "val"})
        assert result == b"docx_bytes"

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_get_request(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        mock_instance = MagicMock()
        mock_instance.get.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        result = client._get("/health")
        assert result == {"status": "ok"}

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_health_check_ok(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        mock_instance = MagicMock()
        mock_instance.get.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        assert client.health_check() is True

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_health_check_fail(self, MockClient):
        client = self._make()
        MockClient.side_effect = Exception("connection refused")
        assert client.health_check() is False

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_generate_complaint(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.content = b"complaint_bytes"
        mock_instance = MagicMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        result = client.generate_complaint({"plaintiffName": "test"})
        assert result == b"complaint_bytes"

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_generate_report(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.content = b"report_bytes"
        mock_instance = MagicMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        result = client.generate_report({"projectName": "test"})
        assert result == b"report_bytes"

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_render_template(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.content = b"template_bytes"
        mock_instance = MagicMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        result = client.render_template("template.docx", {"key": "val"})
        assert result == b"template_bytes"

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_list_templates(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"templates": ["a.docx", "b.docx"]}
        mock_instance = MagicMock()
        mock_instance.get.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        result = client.list_templates()
        assert result == ["a.docx", "b.docx"]

    @patch("apps.core.services.poi_client.httpx.Client")
    def test_format_contract(self, MockClient):
        client = self._make()
        mock_resp = MagicMock()
        mock_resp.content = b"formatted_bytes"
        mock_instance = MagicMock()
        mock_instance.post.return_value = mock_resp
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockClient.return_value = mock_instance
        result = client.format_contract(b"original", config={"font": "Arial"})
        assert result == b"formatted_bytes"


class TestGetPoiClient:
    def test_singleton(self):
        import apps.core.services.poi_client as mod
        old = mod._default_client
        mod._default_client = None
        try:
            client = get_poi_client()
            assert isinstance(client, POIServiceClient)
            client2 = get_poi_client()
            assert client is client2
        finally:
            mod._default_client = old
