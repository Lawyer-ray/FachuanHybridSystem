"""
Core Quality Uplift 测试

属性测试（Property 1-4）和单元测试，验证 core-quality-uplift 的所有修改。

Validates: Requirements 1.1-1.6, 2.1-2.4, 3.1-3.5, 4.1-4.5, 5.1-5.4, 6.1-6.2
"""

from __future__ import annotations

import ast
import inspect
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

logger = logging.getLogger(__name__)

# ==================== 路径常量 ====================

CORE_DIR = Path(__file__).resolve().parent.parent


# ==================== Property 1: SystemConfigService 写操作缓存清除不变量 ====================


class TestSystemConfigServiceCacheClear:
    """
    Property 1: SystemConfigService 写操作缓存清除不变量

    对于 SystemConfigService 的写操作方法（set_value），操作完成后对应 key 的缓存应被清除。

    **Validates: Requirements 1.6**
    """

    @given(
        key=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
            min_size=1,
            max_size=50,
        ),
        value=st.text(min_size=0, max_size=200),
    )
    @h_settings(max_examples=100, deadline=None)
    @pytest.mark.django_db(transaction=True)
    def test_set_value_clears_cache(self, key: str, value: str) -> None:
        """set_value 操作后，对应 key 的缓存应被清除"""
        from django.core.cache import cache

        from apps.core.services.system_config_service import SystemConfigService

        service = SystemConfigService()
        cache_key = f"system_config:{key}"

        # 预设缓存
        cache.set(cache_key, "stale_value", timeout=60)
        assert cache.get(cache_key) == "stale_value"

        # 执行写操作
        service.set_value(key=key, value=value)

        # 验证缓存已清除
        cached = cache.get(cache_key)
        assert cached is None, f"set_value 后缓存未清除: key={key!r}, cached={cached!r}"

        # 清理
        from apps.core.models.system_config import SystemConfig

        SystemConfig.objects.filter(key=key).delete()


# ==================== Property 2: 必要中间件保留不变量 ====================


class TestRequiredMiddlewaresPreserved:
    """
    Property 2: 必要中间件保留不变量

    RequestMetricsMiddleware、SecurityHeadersMiddleware、PermissionsPolicyMiddleware、
    ServiceLocatorScopeMiddleware 可从 middleware 模块导入。

    **Validates: Requirements 4.5**
    """

    REQUIRED_MIDDLEWARES: list[str] = [
        "RequestMetricsMiddleware",
        "SecurityHeadersMiddleware",
        "PermissionsPolicyMiddleware",
        "ServiceLocatorScopeMiddleware",
    ]

    @given(idx=st.sampled_from(list(range(4))))
    @h_settings(max_examples=100, deadline=None)
    def test_required_middleware_importable(self, idx: int) -> None:
        """必要中间件可从 middleware 模块导入"""
        from apps.core import middleware

        name = self.REQUIRED_MIDDLEWARES[idx]
        cls = getattr(middleware, name, None)
        assert cls is not None, f"{name} 无法从 apps.core.middleware 导入"
        assert inspect.isclass(cls), f"{name} 不是类"


# ==================== Property 3: _parse_bool 行为保持 ====================


# 策略：生成各种类型的输入
_truthy_strings = st.sampled_from(["1", "true", "yes", "y", "on", "True", "TRUE", "YES", "Y", "ON"])
_falsy_strings = st.sampled_from(["0", "false", "no", "n", "off", "False", "FALSE", "NO", "N", "OFF"])
_other_strings = st.sampled_from(["abc", "xyz", "hello", "maybe", "2", "99", "-1", "null", "none", "unknown"])
_parse_bool_values: st.SearchStrategy[Any] = st.one_of(
    st.booleans(),
    st.none(),
    st.just(""),
    _truthy_strings,
    _falsy_strings,
    _other_strings,
    st.integers(min_value=-100, max_value=100),
)


def _expected_parse_bool(value: Any, default: bool) -> bool:
    """_parse_bool 的参考实现"""
    if isinstance(value, bool):
        return value
    if not value:
        return default
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default


class TestParseBoolBehavior:
    """
    Property 3: _parse_bool 行为保持

    生成随机输入值，验证 _parse_bool 返回值符合规范。

    **Validates: Requirements 5.4**
    """

    @given(value=_parse_bool_values, default=st.booleans())
    @h_settings(max_examples=100, deadline=None)
    def test_parse_bool_matches_spec(self, value: Any, default: bool) -> None:
        """_parse_bool 返回值符合规范"""
        from apps.core.llm.config import LLMConfig

        result = LLMConfig._parse_bool(value, default)
        expected = _expected_parse_bool(value, default)
        assert result == expected, (
            f"_parse_bool({value!r}, {default!r}) = {result!r}, expected {expected!r}"
        )


# ==================== Property 4: _parse_int 行为保持 ====================


_parse_int_values: st.SearchStrategy[Any] = st.one_of(
    st.none(),
    st.just(""),
    st.integers(min_value=-10000, max_value=10000),
    st.integers(min_value=-10000, max_value=10000).map(str),
    st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    st.sampled_from(["abc", "xyz", "hello", "not_a_number", "3.14", "1e2"]),
)


def _expected_parse_int(value: Any, default: int) -> int:
    """_parse_int 的参考实现"""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class TestParseIntBehavior:
    """
    Property 4: _parse_int 行为保持

    生成随机输入值，验证 _parse_int 返回值符合规范。

    **Validates: Requirements 5.4**
    """

    @given(value=_parse_int_values, default=st.integers(min_value=-1000, max_value=1000))
    @h_settings(max_examples=100, deadline=None)
    def test_parse_int_matches_spec(self, value: Any, default: int) -> None:
        """_parse_int 返回值符合规范"""
        from apps.core.llm.config import LLMConfig

        result = LLMConfig._parse_int(value, default)
        expected = _expected_parse_int(value, default)
        assert result == expected, (
            f"_parse_int({value!r}, {default!r}) = {result!r}, expected {expected!r}"
        )


# ==================== 7.5 单元测试验证所有验收标准 ====================


class TestAcceptanceCriteria:
    """
    单元测试验证所有验收标准

    Validates: Requirements 1.1-1.6, 2.1-2.4, 3.1-3.5, 4.1-4.5, 5.1-5.4, 6.1-6.2
    """

    def test_system_config_is_pure_model(self) -> None:
        """SystemConfig 是纯 Model，无业务方法（get_value、set_value 等）"""
        from apps.core.models import SystemConfig

        forbidden_methods = ["get_value", "set_value", "get_category_configs"]
        for method_name in forbidden_methods:
            attr = getattr(SystemConfig, method_name, None)
            # 允许 Django 内置方法（如 get_xxx_display），但不允许自定义业务方法
            if attr is not None:
                # 确认不是在 SystemConfig 自身定义的
                assert method_name not in SystemConfig.__dict__, (
                    f"SystemConfig 不应包含业务方法 {method_name}"
                )

    def test_legacy_files_deleted(self) -> None:
        """exceptions_types.py、health.py、models.py（根文件）不存在"""
        files_should_not_exist = [
            CORE_DIR / "exceptions_types.py",
            CORE_DIR / "health.py",
            CORE_DIR / "models.py",
        ]
        for filepath in files_should_not_exist:
            assert not filepath.exists(), f"文件应已删除: {filepath}"

    def test_middleware_no_performance_monitoring(self) -> None:
        """middleware.py 中不包含 PerformanceMonitoringMiddleware"""
        middleware_file = CORE_DIR / "middleware.py"
        assert middleware_file.exists(), "middleware.py 应存在"

        source = middleware_file.read_text(encoding="utf-8")

        # AST 检查：不存在名为 PerformanceMonitoringMiddleware 的类定义
        tree = ast.parse(source)
        class_names = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ]
        assert "PerformanceMonitoringMiddleware" not in class_names, (
            "middleware.py 不应包含 PerformanceMonitoringMiddleware 类"
        )

    def test_parse_bool_is_classmethod(self) -> None:
        """_parse_bool 是 classmethod"""
        from apps.core.llm.config import LLMConfig

        attr = inspect.getattr_static(LLMConfig, "_parse_bool")
        assert isinstance(attr, classmethod), (
            f"_parse_bool 应为 classmethod，实际为 {type(attr).__name__}"
        )

    def test_parse_int_is_classmethod(self) -> None:
        """_parse_int 是 classmethod"""
        from apps.core.llm.config import LLMConfig

        attr = inspect.getattr_static(LLMConfig, "_parse_int")
        assert isinstance(attr, classmethod), (
            f"_parse_int 应为 classmethod，实际为 {type(attr).__name__}"
        )

    def test_checker_class_has_staticmethod_comment(self) -> None:
        """_checker_class.py 中 staticmethod 赋值处有说明注释"""
        checker_file = CORE_DIR / "infrastructure" / "health" / "_checker_class.py"
        assert checker_file.exists(), "_checker_class.py 应存在"

        source = checker_file.read_text(encoding="utf-8")

        # 验证包含 staticmethod() 赋值
        assert "staticmethod(" in source, "_checker_class.py 应包含 staticmethod() 赋值"

        # 验证在 staticmethod 赋值附近有 NOTE 注释
        assert "NOTE:" in source or "NOTE：" in source, (
            "_checker_class.py 的 staticmethod 赋值处应有 NOTE 注释说明"
        )

        # 验证注释内容提到基础设施层
        assert "基础设施" in source or "infrastructure" in source.lower(), (
            "注释应说明基础设施层允许使用 staticmethod"
        )
