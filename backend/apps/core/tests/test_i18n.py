"""i18n 国际化测试套件"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from django.apps import apps
from django.conf import settings
from django.test import Client, RequestFactory, TestCase
from django.utils.functional import Promise
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from apps.core.exceptions import ValidationException
from apps.core.services.i18n_service import I18nService


# ─── Property 1: Model verbose_name 国际化完整性 ──────────────────────────────

class TestModelVerboseNameI18n(TestCase):
    """遍历所有 app 的 Model，检查 verbose_name 是否为 lazy string"""

    SKIP_APPS = {"admin", "auth", "contenttypes", "sessions", "flatpages", "django_q"}

    def test_all_model_verbose_names_are_lazy(self) -> None:
        non_lazy: list[str] = []
        for model in apps.get_models():
            meta = model._meta
            if meta.app_label in self.SKIP_APPS:
                continue
            vn = meta.verbose_name
            if not isinstance(vn, Promise):
                non_lazy.append(
                    f"{meta.app_label}.{meta.model_name}: verbose_name={vn!r}"
                )
        self.assertEqual(
            non_lazy,
            [],
            msg="以下 Model 的 verbose_name 未使用 gettext_lazy:\n"
            + "\n".join(non_lazy),
        )


# ─── Property 2: 语言切换 API 幂等性 ─────────────────────────────────────────

class TestLanguageSwitchIdempotency(HypothesisTestCase):
    """连续两次设置相同语言，结果应与调用一次相同"""

    @given(lang=st.sampled_from(["zh-hans", "en"]))
    @h_settings(max_examples=10)
    def test_set_language_twice_same_result(self, lang: str) -> None:
        service = I18nService()

        def make_mock_request() -> Any:
            req = MagicMock()
            req.session = {}
            return req

        req1 = make_mock_request()
        service.set_language(req1, lang)
        result1 = req1.session.get("django_language")

        req2 = make_mock_request()
        service.set_language(req2, lang)
        service.set_language(req2, lang)
        result2 = req2.session.get("django_language")

        self.assertEqual(result1, result2)


# ─── Property 3: 不支持的语言代码拒绝 ────────────────────────────────────────

class TestUnsupportedLanguageRejection(HypothesisTestCase):
    """任意不在 LANGUAGES 列表中的语言代码应抛出 ValidationException"""

    SUPPORTED = {code for code, _ in settings.LANGUAGES}

    @given(
        lang=st.text(min_size=1, max_size=20).filter(
            lambda s: s.isascii() and s not in {"zh-hans", "en"}
        )
    )
    @h_settings(max_examples=50)
    def test_unsupported_language_raises(self, lang: str) -> None:
        if lang in self.SUPPORTED:
            return
        service = I18nService()
        req = MagicMock()
        req.session = {}
        with self.assertRaises(ValidationException):
            service.set_language(req, lang)


# ─── Property 4: Accept-Language 回退到默认语言 ───────────────────────────────

class TestAcceptLanguageFallback(TestCase):
    """Accept-Language 为空或不支持时应使用 LANGUAGE_CODE (zh-hans)"""

    def test_empty_accept_language_uses_default(self) -> None:
        from django.utils.translation import get_language_from_request

        factory = RequestFactory()
        request = factory.get("/", HTTP_ACCEPT_LANGUAGE="")
        lang = get_language_from_request(request)
        self.assertEqual(lang, settings.LANGUAGE_CODE)

    def test_unsupported_accept_language_uses_default(self) -> None:
        from django.utils.translation import get_language_from_request

        factory = RequestFactory()
        request = factory.get("/", HTTP_ACCEPT_LANGUAGE="xx-XX,xx;q=0.9")
        lang = get_language_from_request(request)
        self.assertEqual(lang, settings.LANGUAGE_CODE)


# ─── 单元测试: I18nService ────────────────────────────────────────────────────

class TestI18nService(TestCase):
    """语言切换 Service 单元测试"""

    def setUp(self) -> None:
        self.service = I18nService()
        self.req = MagicMock()
        self.req.session = {}

    def test_get_supported_languages_returns_list(self) -> None:
        langs = self.service.get_supported_languages()
        self.assertIsInstance(langs, list)
        self.assertGreater(len(langs), 0)

    def test_get_supported_languages_contains_zh_hans(self) -> None:
        codes = [lang["code"] for lang in self.service.get_supported_languages()]
        self.assertIn("zh-hans", codes)

    def test_get_supported_languages_contains_en(self) -> None:
        codes = [lang["code"] for lang in self.service.get_supported_languages()]
        self.assertIn("en", codes)

    def test_set_language_en_saves_to_session(self) -> None:
        self.service.set_language(self.req, "en")
        self.assertEqual(self.req.session["django_language"], "en")

    def test_set_language_zh_hans_saves_to_session(self) -> None:
        self.service.set_language(self.req, "zh-hans")
        self.assertEqual(self.req.session["django_language"], "zh-hans")

    def test_set_language_invalid_raises(self) -> None:
        with self.assertRaises(ValidationException):
            self.service.set_language(self.req, "fr")

    def test_set_language_empty_raises(self) -> None:
        with self.assertRaises(ValidationException):
            self.service.set_language(self.req, "")


# ─── 单元测试: API 端点 ───────────────────────────────────────────────────────

class TestI18nApiEndpoints(TestCase):
    """语言切换 API 端点测试"""

    def setUp(self) -> None:
        self.client = Client()

    def test_get_languages_returns_200(self) -> None:
        resp = self.client.get("/api/v1/i18n/languages")
        self.assertEqual(resp.status_code, 200)

    def test_get_languages_response_has_languages_key(self) -> None:
        import json
        resp = self.client.get("/api/v1/i18n/languages")
        data = json.loads(resp.content)
        # ninja 直接返回 list
        self.assertIsInstance(data, list)

    def test_get_languages_contains_zh_hans(self) -> None:
        import json
        resp = self.client.get("/api/v1/i18n/languages")
        data = json.loads(resp.content)
        codes = [item["code"] for item in data]
        self.assertIn("zh-hans", codes)

    def test_post_language_invalid_returns_error(self) -> None:
        import json
        resp = self.client.post(
            "/api/v1/i18n/language",
            data=json.dumps({"language": "fr"}),
            content_type="application/json",
        )
        # 未认证应返回 401，或语言无效返回 400
        self.assertIn(resp.status_code, [400, 401, 422])
