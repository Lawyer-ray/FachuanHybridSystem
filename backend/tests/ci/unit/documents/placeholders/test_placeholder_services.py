"""文档占位符服务测试。"""

from __future__ import annotations

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.fallback import (
    PLACEHOLDER_FALLBACK_VALUE,
    build_docx_render_context,
    ensure_required_placeholders,
    get_service_placeholder_keys,
    normalize_placeholder_value,
    normalize_service_result,
    resolve_render_variable,
)
from apps.documents.services.placeholders.types import PlaceholderContextData


class _ConcretePlaceholderService(BasePlaceholderService):
    """测试用具体占位符服务。"""

    name = "test_service"
    display_name = "测试服务"
    description = "测试用占位符服务"
    category = "basic"
    placeholder_keys = ["test_key1", "test_key2"]
    placeholder_metadata = {
        "test_key1": {"label": "测试键1", "type": "string"},
        "test_key2": {"label": "测试键2", "type": "string"},
    }

    def generate(self, context_data):
        return {"test_key1": "value1", "test_key2": "value2"}


class TestBasePlaceholderService:
    """BasePlaceholderService 测试。"""

    def setup_method(self) -> None:
        self.service = _ConcretePlaceholderService()

    def test_get_placeholder_keys(self) -> None:
        keys = self.service.get_placeholder_keys()
        assert keys == ["test_key1", "test_key2"]

    def test_get_placeholder_keys_returns_copy(self) -> None:
        """返回副本不影响原始列表。"""
        keys = self.service.get_placeholder_keys()
        keys.append("extra")
        assert len(self.service.get_placeholder_keys()) == 2

    def test_get_placeholder_metadata(self) -> None:
        meta = self.service.get_placeholder_metadata()
        assert "test_key1" in meta
        assert meta["test_key1"]["label"] == "测试键1"

    def test_generate(self) -> None:
        result = self.service.generate({})
        assert result["test_key1"] == "value1"
        assert result["test_key2"] == "value2"

    def test_str(self) -> None:
        assert "test_service" in str(self.service)

    def test_repr(self) -> None:
        assert "test_service" in repr(self.service)


class TestFallback:
    """占位符兜底工具测试。"""

    def test_normalize_placeholder_value_none(self) -> None:
        assert normalize_placeholder_value(None) == PLACEHOLDER_FALLBACK_VALUE

    def test_normalize_placeholder_value_empty_string(self) -> None:
        assert normalize_placeholder_value("") == PLACEHOLDER_FALLBACK_VALUE

    def test_normalize_placeholder_value_whitespace(self) -> None:
        assert normalize_placeholder_value("   ") == PLACEHOLDER_FALLBACK_VALUE

    def test_normalize_placeholder_value_valid(self) -> None:
        assert normalize_placeholder_value("hello") == "hello"
        assert normalize_placeholder_value(42) == 42
        assert normalize_placeholder_value(0) == 0

    def test_get_service_placeholder_keys_with_getter(self) -> None:
        """服务有 get_placeholder_keys 方法。"""
        service = _ConcretePlaceholderService()
        keys = get_service_placeholder_keys(service)
        assert keys == ["test_key1", "test_key2"]

    def test_get_service_placeholder_keys_without_getter(self) -> None:
        """服务没有 get_placeholder_keys 方法，使用属性。"""
        service = type("Svc", (), {"placeholder_keys": ["key1", "key2"]})()
        keys = get_service_placeholder_keys(service)
        assert keys == ["key1", "key2"]

    def test_get_service_placeholder_keys_no_keys(self) -> None:
        """服务没有 keys。"""
        service = type("Svc", (), {})()
        keys = get_service_placeholder_keys(service)
        assert keys == []

    def test_normalize_service_result(self) -> None:
        result = normalize_service_result(
            {"key1": "value1", "key2": None},
            expected_keys=["key1", "key2", "key3"],
        )
        assert result["key1"] == "value1"
        assert result["key2"] == PLACEHOLDER_FALLBACK_VALUE
        assert result["key3"] == PLACEHOLDER_FALLBACK_VALUE

    def test_normalize_service_result_none(self) -> None:
        result = normalize_service_result(None, expected_keys=["key1"])
        assert result["key1"] == PLACEHOLDER_FALLBACK_VALUE

    def test_ensure_required_placeholders(self) -> None:
        context = {"name": "张三", "address": None}
        result = ensure_required_placeholders(context, ["name", "address", "phone"])
        assert result["name"] == "张三"
        assert result["address"] == PLACEHOLDER_FALLBACK_VALUE
        assert result["phone"] == PLACEHOLDER_FALLBACK_VALUE

    def test_resolve_render_variable_found(self) -> None:
        hit, value = resolve_render_variable({"name": "张三"}, "name")
        assert hit is True
        assert value == "张三"

    def test_resolve_render_variable_none(self) -> None:
        hit, value = resolve_render_variable({"name": None}, "name")
        assert hit is False
        assert value == PLACEHOLDER_FALLBACK_VALUE

    def test_resolve_render_variable_missing(self) -> None:
        hit, value = resolve_render_variable({}, "name")
        assert hit is False
        assert value == PLACEHOLDER_FALLBACK_VALUE


class _DocStub:
    """docxtpl 文档存根。"""

    def get_undeclared_template_variables(self, context=None):
        if context and "known" in context:
            return {"missing_key"}
        return set()


class TestBuildDocxRenderContext:
    """build_docx_render_context 测试。"""

    def test_fills_undeclared_variables(self) -> None:
        context = build_docx_render_context(doc=_DocStub(), context={"known": "ok"})
        assert context["known"] == "ok"
        assert context["missing_key"] == PLACEHOLDER_FALLBACK_VALUE

    def test_no_undeclared_variables(self) -> None:
        context = build_docx_render_context(doc=_DocStub(), context={})
        assert "known" not in context

    def test_custom_fallback_value(self) -> None:
        context = build_docx_render_context(
            doc=_DocStub(), context={"known": "ok"}, fallback_value="N/A"
        )
        assert context["missing_key"] == "N/A"


class TestPlaceholderContextData:
    """PlaceholderContextData TypedDict 测试。"""

    def test_create_context(self) -> None:
        ctx: PlaceholderContextData = {
            "contract_id": 1,
            "case_id": 2,
            "split_fee": True,
        }
        assert ctx["contract_id"] == 1
        assert ctx["case_id"] == 2
        assert ctx["split_fee"] is True
