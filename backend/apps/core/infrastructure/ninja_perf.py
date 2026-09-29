"""Ninja Schema 序列化性能补丁。

背景：django-ninja（pydantic v2 兼容层）的 ``DjangoGetter.__getattr__`` 对每次
字段访问都要经历 resolver 查找 → getattr 失败回退 → 构造模板 ``Variable`` →
``_convert_result`` 的 isinstance 链，且不做任何缓存（上游源码注释自认该缓存）。
列表接口的代价随行数线性放大：实测收件箱 345 条 × 18 字段的序列化里，
该路径占请求耗时的大头（单请求约 6.5 万次 ``__getattr__``）。

补丁策略（对单个短命 DjangoGetter 实例做字段级 memo）：

- 命中过的字段写入实例 ``__dict__``。Python 属性查找先于 ``__getattr__``
  查实例字典，因此重复访问（pydantic 校验/转换阶段会对同一字段多次取值）
  直接短路，不再进入本函数。
- 对非 dict 对象先用原生 ``getattr`` 直取，失败才回落到模板 ``Variable``
  解析，与上游语义一致。
- 校验失败（AttributeError）不缓存，保持异常语义不变。

DjangoGetter 每次校验新建、随请求丢弃，缓存不跨请求存活，无泄漏风险。
若 ninja 升级后内部结构变化（无 ``_ninja_resolvers`` / ``Variable``），补丁
自动跳过，回退上游实现。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MISSING = object()


def patch_django_getter_for_perf() -> bool:
    """给 ninja.schema.DjangoGetter 打属性缓存补丁，返回是否生效。"""
    try:
        from ninja import schema as ninja_schema
    except ImportError:  # pragma: no cover - ninja 缺失时无从谈起
        logger.debug("ninja 未安装，跳过 DjangoGetter 性能补丁")
        return False

    getter_cls = getattr(ninja_schema, "DjangoGetter", None)
    variable_cls = getattr(ninja_schema, "Variable", None)
    if getter_cls is None or variable_cls is None:  # pragma: no cover - 上游结构变化
        logger.warning("ninja DjangoGetter 结构与预期不符，跳过性能补丁")
        return False
    if getattr(getter_cls, "_fachuan_perf_patched", False):
        return True

    original_getattr = getter_cls.__getattr__
    convert_result = getter_cls._convert_result
    variable_does_not_exist = ninja_schema.VariableDoesNotExist

    def fast_getattr(self: Any, key: str) -> Any:
        cached = self.__dict__.get(key, _MISSING)
        if cached is not _MISSING:
            return cached
        resolver = self._schema_cls._ninja_resolvers.get(key)
        if resolver:
            value = resolver(getter=self)
        else:
            obj = self._obj
            if isinstance(obj, dict):
                if key not in obj:
                    raise AttributeError(key)
                value = obj[key]
            else:
                try:
                    value = getattr(obj, key)
                except AttributeError:
                    try:
                        value = variable_cls(key).resolve(obj)
                    except variable_does_not_exist as e:
                        raise AttributeError(key) from e
        value = convert_result(self, value)
        self.__dict__[key] = value
        return value

    fast_getattr._fachuan_perf_patched = True  # type: ignore[attr-defined]
    fast_getattr._upstream = original_getattr  # type: ignore[attr-defined]
    getter_cls.__getattr__ = fast_getattr
    logger.info("ninja DjangoGetter 性能补丁已应用（字段级缓存）")
    return True
