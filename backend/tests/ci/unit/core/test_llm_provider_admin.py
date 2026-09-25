"""LLMProviderAdmin「获取远端模型列表」接口测试。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.core.admin.llm_provider_admin import LLMProviderAdmin
from apps.core.models import LLMProvider
from apps.core.services.llm_provider_service import LLMProviderService, RemoteKeyModels, RemoteModelList

User = get_user_model()


def _admin() -> LLMProviderAdmin:
    return LLMProviderAdmin(LLMProvider, AdminSite())


def _request(method: str = "post", payload: dict[str, Any] | None = None) -> Any:
    factory = RequestFactory()
    path = "/admin/core/llmprovider/1/fetch-models/"
    if method == "post":
        request = factory.post(path, data=json.dumps(payload or {}), content_type="application/json")
    else:
        request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


def _fake_result(base_url: str, api_keys: list[str] | None = None) -> RemoteModelList:
    return RemoteModelList(
        url=f"{base_url.rstrip('/')}/models",
        per_key=[RemoteKeyModels(index=1, ok=True, models=["m1", "m2"])],
        models=["m1", "m2"],
        common_models=["m1"],
    )


class TestFetchModelsView:
    def test_rejects_non_post(self) -> None:
        response = _admin().fetch_models_view(_request("get"), "1")

        assert response.status_code == 405
        assert json.loads(response.content)["ok"] is False

    def test_rejects_without_change_permission(self, monkeypatch: pytest.MonkeyPatch) -> None:
        admin_obj = _admin()
        monkeypatch.setattr(admin_obj, "has_change_permission", lambda *args, **kwargs: False)

        response = admin_obj.fetch_models_view(_request(), "1")

        assert response.status_code == 403

    def test_requires_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: Any, **kwargs: Any) -> RemoteModelList:
            raise AssertionError("缺少 API 地址时不应发起探测")

        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", boom)

        response = _admin().fetch_models_view(_request(payload={"base_url": "   "}), "add")

        assert response.status_code == 400
        assert json.loads(response.content)["error"] == "请先填写 API 地址"

    def test_uses_payload_values_and_parses_key_scopes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_fetch(
            base_url: str, api_keys: list[str] | None = None, timeout: float | None = None
        ) -> RemoteModelList:
            captured["base_url"] = base_url
            captured["api_keys"] = api_keys
            return _fake_result(base_url, api_keys)

        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", fake_fetch)

        response = _admin().fetch_models_view(
            _request(payload={"base_url": "http://gw/v1", "api_keys": "sk-a|m1\nsk-b"}),  # pragma: allowlist secret
            "add",
        )

        assert response.status_code == 200
        assert captured["base_url"] == "http://gw/v1"
        # 含 | 的白名单被剥离，只把 Key 交给探测
        assert captured["api_keys"] == ["sk-a", "sk-b"]
        body = json.loads(response.content)
        assert body["ok"] is True
        assert body["models"] == ["m1", "m2"]
        assert body["common_models"] == ["m1"]
        assert body["per_key"] == [{"index": 1, "ok": True, "models": ["m1", "m2"], "error": ""}]

    @pytest.mark.django_db
    def test_falls_back_to_saved_provider_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = LLMProvider.objects.create(
            name="律所 kimi",
            base_url="http://saved/v1",
            api_keys="sk-saved",  # pragma: allowlist secret
            default_model="kimi-2.6",
        )
        captured: dict[str, Any] = {}

        def fake_fetch(
            base_url: str, api_keys: list[str] | None = None, timeout: float | None = None
        ) -> RemoteModelList:
            captured["base_url"] = base_url
            captured["api_keys"] = api_keys
            return _fake_result(base_url, api_keys)

        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", fake_fetch)

        response = _admin().fetch_models_view(_request(payload={}), str(provider.pk))

        assert response.status_code == 200
        assert captured["base_url"] == "http://saved/v1"
        assert captured["api_keys"] == ["sk-saved"]

    def test_malformed_json_body_is_tolerated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            LLMProviderService,
            "fetch_remote_models",
            lambda base_url, api_keys=None, timeout=None: _fake_result(base_url, api_keys),
        )
        factory = RequestFactory()
        request = factory.post(
            "/admin/core/llmprovider/1/fetch-models/",
            data=b"{not-json",
            content_type="application/json",
        )
        request.user = User(is_superuser=True, is_staff=True)

        # 非法 JSON 视为空 payload，随后因缺 base_url 返回 400 而非 500
        response = _admin().fetch_models_view(request, "add")

        assert response.status_code == 400

    def test_reports_all_keys_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            LLMProviderService,
            "fetch_remote_models",
            lambda base_url, api_keys=None, timeout=None: RemoteModelList(
                url=f"{base_url}/models",
                per_key=[RemoteKeyModels(index=1, ok=False, error="HTTP 403")],
                models=[],
                common_models=[],
            ),
        )

        response = _admin().fetch_models_view(
            _request(payload={"base_url": "http://gw/v1", "api_keys": "sk-a"}),  # pragma: allowlist secret
            "add",
        )

        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["ok"] is False
        assert body["per_key"][0]["error"] == "HTTP 403"
