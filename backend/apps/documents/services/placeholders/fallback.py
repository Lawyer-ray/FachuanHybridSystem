"""占位符统一兜底工具。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

PLACEHOLDER_FALLBACK_VALUE = "/"


def normalize_placeholder_value(value: Any, *, fallback_value: str = PLACEHOLDER_FALLBACK_VALUE) -> Any:
    """将 None 和空字符串统一归一为兜底值。"""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return fallback_value
    return value


def get_service_placeholder_keys(service: Any) -> list[str]:
    """兼容不同服务实现，提取服务声明的占位符键。"""
    getter = getattr(service, "get_placeholder_keys", None)
    if callable(getter):
        keys = getter()
    else:
        keys = getattr(service, "placeholder_keys", [])

    if not isinstance(keys, Iterable) or isinstance(keys, (str, bytes)):
        return []

    result: list[str] = []
    for key in keys:
        if isinstance(key, str) and key.strip():
            result.append(key)
    return result


def normalize_service_result(
    service_result: Mapping[str, Any] | None,
    *,
    expected_keys: Iterable[str] = (),
    fallback_value: str = PLACEHOLDER_FALLBACK_VALUE,
) -> dict[str, Any]:
    """标准化单个服务的返回值，并补全服务声明但未返回的键。"""
    normalized: dict[str, Any] = {}

    if service_result:
        for key, value in service_result.items():
            normalized[str(key)] = normalize_placeholder_value(value, fallback_value=fallback_value)

    for key in expected_keys:
        normalized.setdefault(key, fallback_value)

    return normalized


def ensure_required_placeholders(
    context: Mapping[str, Any],
    required_placeholders: Iterable[str] | None,
    *,
    fallback_value: str = PLACEHOLDER_FALLBACK_VALUE,
) -> dict[str, Any]:
    """确保 required_placeholders 中所有键都存在且非 None。"""
    normalized: dict[str, Any] = {
        str(key): normalize_placeholder_value(value, fallback_value=fallback_value)
        for key, value in context.items()
    }

    if required_placeholders:
        for key in required_placeholders:
            if key not in normalized or normalized[key] is None:
                normalized[key] = fallback_value

    return normalized


def build_docx_render_context(
    *,
    doc: Any,
    context: Mapping[str, Any],
    fallback_value: str = PLACEHOLDER_FALLBACK_VALUE,
) -> dict[str, Any]:
    """在 docxtpl 渲染前补齐缺失变量，保证模板中未命中的变量也会落为兜底值。"""
    normalized = ensure_required_placeholders(context, None, fallback_value=fallback_value)
    missing_keys = _get_undeclared_template_variables(doc=doc, context=normalized)

    for key in missing_keys:
        normalized.setdefault(key, fallback_value)

    return normalized


def resolve_render_variable(
    variables: Mapping[str, Any],
    key: str,
    *,
    fallback_value: str = PLACEHOLDER_FALLBACK_VALUE,
) -> tuple[bool, str]:
    """字符串模板渲染的统一变量解析。"""
    if key in variables and variables[key] is not None:
        return True, str(variables[key])
    return False, fallback_value


def _get_undeclared_template_variables(*, doc: Any, context: Mapping[str, Any]) -> set[str]:
    getter = getattr(doc, "get_undeclared_template_variables", None)
    if not callable(getter):
        return set()

    values: Any
    try:
        values = getter(context=dict(context))
    except TypeError:
        try:
            values = getter(dict(context))
        except Exception:
            return set()
    except Exception:
        return set()

    if not isinstance(values, (set, list, tuple)):
        return set()

    result: set[str] = set()
    for item in values:
        if isinstance(item, str) and item.strip():
            result.add(item)
    return result
