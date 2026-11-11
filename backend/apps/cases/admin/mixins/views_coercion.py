"""Admin 视图层的请求参数类型强制转换。

HTTP 请求体里的字段一律是字符串/None，视图层需要把它们转成 Service 层要的类型；
转换失败一律返回 None（由 Service 走默认值），不抛异常。纯函数、无 Django 依赖。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation


def _coerce_optional_date(raw: object) -> date | None:  # pragma: no cover
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _coerce_optional_decimal(raw: object) -> Decimal | None:  # pragma: no cover
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _coerce_optional_bool(raw: object) -> bool | None:  # pragma: no cover
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    value = str(raw).strip().lower()
    if not value:
        return None
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _coerce_optional_int(raw: object) -> int | None:  # pragma: no cover
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _coerce_optional_str(raw: object) -> str | None:  # pragma: no cover
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return value


__all__: list[str] = [
    "_coerce_optional_bool",
    "_coerce_optional_date",
    "_coerce_optional_decimal",
    "_coerce_optional_int",
    "_coerce_optional_str",
]
