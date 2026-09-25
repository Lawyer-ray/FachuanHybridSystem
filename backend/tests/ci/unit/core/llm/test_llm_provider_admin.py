"""LLMProviderAdmin「获取远端模型列表」接口测试。

覆盖权限、方法、入参校验，以及 ``probe_chat`` 开关是否透传到 Service。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.urls import reverse

from apps.core.models import LLMProvider
from apps.core.services.llm_provider_service import LLMProviderService, RemoteKeyModels, RemoteModelList


def _url(provider: LLMProvider) -> str:
    return reverse("admin:core_llmprovider_fetch_models", args=[provider.pk])


@pytest.fixture
def provider(db: Any) -> LLMProvider:
    return LLMProvider.objects.create(
        name="测试平台",
        base_url="http://gw.example/v1",
        api_keys="sk-1|kimi-2.6\nsk-2",  # pragma: allowlist secret
        default_model="kimi-2.6",
    )


@pytest.fixture
def admin_user(db: Any) -> Any:
    """本地覆盖 pytest-django 的同名 fixture，走 LawyerManager.create_superuser 的显式签名。"""
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_superuser(
        username="llm_admin",
        email=None,
        password="testpass1234!",  # pragma: allowlist secret
    )


def _fake_result(**overrides: Any) -> RemoteModelList:
    base = RemoteModelList(
        url="http://gw.example/v1/models",
        per_key=[RemoteKeyModels(index=1, ok=True, models=["kimi-2.6"])],
        models=["kimi-2.6"],
        common_models=["kimi-2.6"],
        chat_models=["kimi-2.6"],
    )
    for name, value in overrides.items():
        setattr(base, name, value)
    return base


class TestFetchModelsViewGuards:
    """权限与请求方法守卫。"""

    @pytest.mark.django_db
    def test_anonymous_is_redirected_to_login(self, client: Any, provider: LLMProvider) -> None:
        response = client.post(_url(provider), data="{}", content_type="application/json")
        assert response.status_code == 302
        assert "/admin/login/" in response["Location"]

    @pytest.mark.django_db
    def test_staff_without_change_permission_is_forbidden(self, client: Any, provider: LLMProvider) -> None:
        from apps.organization.models import Lawyer

        staff = Lawyer.objects.create_user(
            username="llm_staff_no_perm",
            password="testpass1234!",  # pragma: allowlist secret
            is_staff=True,
        )
        client.force_login(staff)
        response = client.post(_url(provider), data="{}", content_type="application/json")
        assert response.status_code == 403
        assert response.json()["ok"] is False

    @pytest.mark.django_db
    def test_get_method_is_rejected(self, client: Any, provider: LLMProvider, admin_user: Any) -> None:
        client.force_login(admin_user)
        response = client.get(_url(provider))
        assert response.status_code == 405

    @pytest.mark.django_db
    def test_missing_base_url_returns_400(
        self, client: Any, provider: LLMProvider, admin_user: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider.base_url = ""
        provider.save(update_fields=["base_url"])

        def _unexpected(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("base_url 为空时不应调用 Service")

        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", classmethod(_unexpected))
        client.force_login(admin_user)
        response = client.post(_url(provider), data="{}", content_type="application/json")
        assert response.status_code == 400
        assert response.json()["error"] == "请先填写 API 地址"


class TestFetchModelsPayload:
    """入参解析与响应结构。"""

    @pytest.mark.django_db
    def test_form_values_take_precedence_over_saved_row(
        self, client: Any, provider: LLMProvider, admin_user: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(cls: Any, base_url: str, api_keys: list[str] | None = None, timeout: Any = None, **kwargs: Any) -> Any:
            captured["base_url"] = base_url
            captured["api_keys"] = api_keys
            return _fake_result()

        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", classmethod(fake))
        client.force_login(admin_user)
        response = client.post(
            _url(provider),
            data=json.dumps({"base_url": "http://other.example/v1", "api_keys": "sk-form"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert captured["base_url"] == "http://other.example/v1"
        assert captured["api_keys"] == ["sk-form"]

    @pytest.mark.django_db
    def test_falls_back_to_saved_row_when_payload_is_empty(
        self, client: Any, provider: LLMProvider, admin_user: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(cls: Any, base_url: str, api_keys: list[str] | None = None, timeout: Any = None, **kwargs: Any) -> Any:
            captured["base_url"] = base_url
            captured["api_keys"] = api_keys
            return _fake_result()

        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", classmethod(fake))
        client.force_login(admin_user)
        client.post(_url(provider), data="{}", content_type="application/json")

        assert captured["base_url"] == "http://gw.example/v1"
        assert captured["api_keys"] == ["sk-1", "sk-2"]

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({}, True),
            ({"probe_chat": False}, False),
            ({"probe_chat": True}, True),
            ({"probe_chat": "false"}, False),
        ],
    )
    def test_probe_chat_flag_is_forwarded(
        self,
        client: Any,
        provider: LLMProvider,
        admin_user: Any,
        monkeypatch: pytest.MonkeyPatch,
        payload: dict[str, Any],
        expected: bool,
    ) -> None:
        captured: dict[str, Any] = {}

        def fake(cls: Any, base_url: str, api_keys: list[str] | None = None, timeout: Any = None, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return _fake_result()

        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", classmethod(fake))
        client.force_login(admin_user)
        client.post(_url(provider), data=json.dumps(payload), content_type="application/json")

        assert captured["probe_chat"] is expected

    @pytest.mark.django_db
    def test_response_exposes_per_key_detail(
        self, client: Any, provider: LLMProvider, admin_user: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = _fake_result(
            per_key=[
                RemoteKeyModels(index=1, ok=True, models=["kimi-2.6"]),
                RemoteKeyModels(index=2, ok=False, error="HTTP 403"),
            ],
            models=["kimi-2.6"],
            common_models=["kimi-2.6"],
            chat_models=["kimi-2.6"],
        )
        monkeypatch.setattr(LLMProviderService, "fetch_remote_models", classmethod(lambda cls, *a, **k: result))
        client.force_login(admin_user)
        response = client.post(_url(provider), data="{}", content_type="application/json")
        body = response.json()

        assert body["ok"] is True
        assert body["url"] == "http://gw.example/v1/models"
        assert body["chat_models"] == ["kimi-2.6"]
        assert body["per_key"] == [
            {"index": 1, "ok": True, "models": ["kimi-2.6"], "error": ""},
            {"index": 2, "ok": False, "models": [], "error": "HTTP 403"},
        ]


class TestParseFlag:
    """``_parse_flag`` 的取值规则。"""

    @pytest.mark.parametrize(
        ("raw", "default", "expected"),
        [
            (None, True, True),
            (None, False, False),
            (True, False, True),
            (False, True, False),
            ("on", False, True),
            ("1", False, True),
            ("yes", False, True),
            ("off", True, False),
            ("", True, False),
        ],
    )
    def test_parse_flag(self, raw: Any, default: bool, expected: bool) -> None:
        from apps.core.admin.llm_provider_admin import LLMProviderAdmin

        assert LLMProviderAdmin._parse_flag(raw, default=default) is expected


class TestChangeFormKeyEditor:
    """change_form 模板：行编辑器宿主节点与探测接口地址渲染正确。"""

    @pytest.mark.django_db
    def test_change_form_renders_editor_host(self, client: Any, provider: LLMProvider, admin_user: Any) -> None:
        client.force_login(admin_user)
        response = client.get(reverse("admin:core_llmprovider_change", args=[provider.pk]))

        assert response.status_code == 200
        html = response.content.decode()
        assert 'id="llm-key-editor"' in html
        assert reverse("admin:core_llmprovider_fetch_models", args=[provider.pk]) in html
        assert 'id="id_api_keys"' in html

    @pytest.mark.django_db
    def test_add_form_points_fetch_url_to_add(self, client: Any, admin_user: Any) -> None:
        client.force_login(admin_user)
        response = client.get(reverse("admin:core_llmprovider_add"))

        assert response.status_code == 200
        html = response.content.decode()
        assert reverse("admin:core_llmprovider_fetch_models", args=["add"]) in html

    @pytest.mark.django_db
    def test_editor_script_defers_until_dom_ready(self, client: Any, provider: LLMProvider, admin_user: Any) -> None:
        """脚本位于 <head>（早于宿主节点），因此必须先等 DOMContentLoaded。"""
        client.force_login(admin_user)
        response = client.get(reverse("admin:core_llmprovider_change", args=[provider.pk]))
        html = response.content.decode()

        script_at = html.index('document.addEventListener("DOMContentLoaded", boot)')
        host_at = html.index('id="llm-key-editor"')
        assert script_at < host_at, "脚本应出现在宿主节点之前（这正是必须延迟执行的原因）"
