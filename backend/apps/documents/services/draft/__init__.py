"""一句话起草的规格层：类型 → 骨架 → 槽位取值。

`spec_service` 决定「填哪几个槽、每个槽归谁」，`facts_builder` 决定「有哪些事实可用」。
两者都不渲染、不落盘——渲染与落位是 doc_workspace 的起草用例的事。
"""

from __future__ import annotations

from .facts_builder import build_facts
from .spec_service import LLMCaller, get_spec, list_specs, resolve_slot_values

__all__ = ["LLMCaller", "build_facts", "get_spec", "list_specs", "resolve_slot_values"]
