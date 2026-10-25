"""SSE 事件契约类型（P1-12）——pydantic 定义 → 前端 TS 同源的单一来源。

用法：
    python -m apps.agent.sse_types --ts > frontend/src/features/copilot/sse-events.ts

前端 import type { AgentStreamEvent } from './sse-events' 替代手写 types.ts
中的同名类型（后续批次切换 import 路径即可）。
"""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, Field


class MetaEvent(BaseModel):
    """会话元信息（流开始时一次）"""

    type: Literal["meta"]
    session_id: str
    agent: str = ""


class ActivityEvent(BaseModel):
    """活动状态（thinking / queued）"""

    type: Literal["activity"]
    status: str
    agent: str = ""
    position: int | None = None


class DeltaEvent(BaseModel):
    """正文增量"""

    type: Literal["delta"]
    content: str


class ThinkingEvent(BaseModel):
    """思考增量（不计入正文）"""

    type: Literal["thinking"]
    content: str


class ToolCallEvent(BaseModel):
    """工具调用开始"""

    type: Literal["tool_call"]
    tool_call_id: str
    name: str
    arguments: str | None = None


class ToolResultEvent(BaseModel):
    """工具调用结果"""

    type: Literal["tool_result"]
    tool_call_id: str
    name: str
    result: str | None = None
    is_error: bool = False


class ApprovalRequestEvent(BaseModel):
    """审批请求（高危工具）"""

    type: Literal["approval_request"]
    approval_id: str
    tool_name: str
    tool_args: dict[str, object] = Field(default_factory=dict)
    message: str = ""
    risk_level: str = ""
    needs_second_confirmation: bool = False


class UsageEvent(BaseModel):
    """token 用量（pi 精确计数）。

    ``cache_read_tokens`` / ``cache_write_tokens`` 是 2026-10-25 新增：
    法穿把「AGENTS.md 逐轮字节稳定 → 命中 provider prompt cache」当核心设计，
    但之前账上看不到它到底生效没（``input_tokens`` 只装未命中部分）。
    前端可用 ``cache_read/(input+cache_read+cache_write)`` 算命中率。

    两个 cache 字段带默认 0：旧版 pi / 某些 provider 不上报时不至于断流。
    """

    type: Literal["usage"]
    output_tokens: int
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class ErrorEvent(BaseModel):
    """流内错误（已翻译成人话）"""

    type: Literal["error"]
    message: str


class DoneEvent(BaseModel):
    """流结束"""

    type: Literal["done"]
    session_id: str


AgentStreamEvent = (
    MetaEvent
    | ActivityEvent
    | DeltaEvent
    | ThinkingEvent
    | ToolCallEvent
    | ToolResultEvent
    | ApprovalRequestEvent
    | UsageEvent
    | ErrorEvent
    | DoneEvent
)


def generate_ts() -> str:
    """生成 TypeScript 类型定义文件内容。"""
    return """/**
 * SSE 流事件类型（自动生成——python -m apps.agent.sse_types --ts）
 * 后端单一来源：apps/agent/sse_types.py；修改须同步重新生成。
 */

export type AgentStreamEvent =
  | { type: 'meta'; session_id: string; agent?: string }
  | { type: 'activity'; status: string; agent?: string; position?: number }
  | { type: 'delta'; content: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool_call_id: string; name: string; arguments?: unknown }
  | { type: 'tool_result'; tool_call_id: string; name: string; result?: string; is_error?: boolean }
  | {
      type: 'approval_request'
      approval_id: string
      tool_name: string
      tool_args?: Record<string, unknown>
      message: string
      risk_level?: string
      needs_second_confirmation?: boolean
    }
  | {
      type: 'usage'
      output_tokens: number
      input_tokens: number
      cache_read_tokens: number
      cache_write_tokens: number
    }
  | { type: 'error'; message: string }
  | { type: 'done'; session_id: string }
"""


if __name__ == "__main__":
    if "--ts" in sys.argv:
        sys.stdout.write(generate_ts())
    else:
        # JSON Schema 导出（供 jsonschema 校验）；显式 type[BaseModel] 注解——
        # 联合 type[...] 字面量列表上 mypy 解析不出 pydantic 类方法
        import json

        models: list[type[BaseModel]] = [
            MetaEvent,
            ActivityEvent,
            DeltaEvent,
            ThinkingEvent,
            ToolCallEvent,
            ToolResultEvent,
            ApprovalRequestEvent,
            UsageEvent,
            ErrorEvent,
            DoneEvent,
        ]
        for model in models:
            sys.stdout.write(json.dumps(model.model_json_schema(), indent=2) + "\n")
