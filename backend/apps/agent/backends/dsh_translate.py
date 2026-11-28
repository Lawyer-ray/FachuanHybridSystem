"""dsh 通知 → SSE 契约事件的纯翻译函数（无 IO、无 ``self``、无实例状态）。

## 为什么单独成模块

这五个函数都是「一个 dict 进 → ``list[dict]`` 出」：不读实例字段、不发网络请求、
不碰 SDK，因此可以在不建后端、不连 runtime 的前提下逐条断言（见
``tests/ci/unit/agent/test_dsh_backend.py``）。留在 ``dsh_backend.py`` 里会被
「同步 SDK → SSE 桥」的编排代码淹没，翻译口径本身反而不好审。

## 谁没搬

``_translate`` / ``_translate_event`` / ``_translate_tool_call`` /
``_translate_tool_result`` 留在 :class:`DshBackend`：前两者是分派出口，后两者读写
实例上的 ``_tool_names``（``callId`` → 工具名的配对表——``tool/result`` 事件里没有
工具名，只能靠它配对）。那不是纯函数，搬出来只能靠形参手工穿透实例状态。

## 依赖方向

本模块**不 import ``dsh_backend``**：只允许 ``dsh_backend`` → ``dsh_translate``。
``dsh_backend`` 仍按原名 re-export 这里的五函数，调用方与测试按原路径 import 不受影响。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _log_unmapped(method: str, payload: dict[str, Any]) -> None:
    """未识别的事件记 debug 并原样透传给前端。

    为什么 debug 而不是 warning：dsh 的通知流里有大量内部方法（``session.status``
    / ``session.query.completed`` / ``agent/inbox/spliced`` …），每轮都会刷几十条，
    按 warning 记会把日志淹掉。但**必须记**——接入新版本时这些事件名会变，
    没有日志就只能靠猜。

    为什么透传而不是丢弃：pi 的 bridge 选择静默丢弃（把内部诊断挡在浏览器外），
    dsh 不一样——它的 SDK 是 rc 版本，事件名与字段都还没稳，静默丢弃会让「前端
    少了一栏内容」变成无迹可查。透传 ``unknown`` 让前端能选择忽略，也让联调时
    一眼看到「来了个我们不认识的事件」。**待真实 key 跑一次后按实际事件名收敛**：
    认识的按语义翻译，不认识的再考虑丢。
    """
    logger.debug("dsh 未映射事件 method=%s payload_keys=%s", method, sorted(payload))
    return


def _tool_call_arguments(raw: Any) -> Any:
    """把 dsh 的 ``arguments`` 归一成 ``tool_call`` 帧的 ``arguments``。

    dsh 两个来源都把它写成 **raw JSON 字符串**：assistant 消息里的 ``tool-call``
    块（``packages/llm/src/types.ts``）与 ``tool/call`` 运行事件
    （``session/src/types.ts``）。这里解成对象——参数级展示与审批卡的 ``tool_args``
    都要按键取值。``sse_types.ToolCallEvent.arguments`` 是 ``Any``，前端
    ``extractRewriteArgs`` 对象/字符串都认，所以解成对象不会让任何一侧退化。

    **解不动不抛**：模型偶尔写出不是合法 JSON 的参数（截断、单引号），一个坏参数
    不该让整轮事件流崩掉。原样塞进 ``{"_raw": ...}``，前端至少能显示原文。
    """
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {"_raw": raw}
    return raw if isinstance(raw, dict) else None


def _tool_result_text(content: Any) -> str:
    """把 ``tool/result`` 里的 ``message.content`` 拆成可展示文本。

    形状来自实测的 ``tool/result`` 事件（见 :meth:`DshBackend._translate_tool_result`）：
    ``content`` 是 content block 数组，工具结果的实际载荷在
    ``{"type": "text", "text": ...}`` 块的 ``text`` 里（通常是一段 JSON 字符串）。

    **只取 text 块**：非文本块（图片等）没有可读正文，硬转成 ``str(block)`` 只会
    把 Python repr 泄给前端。与 ``pi/bridge.py`` 的 ``_result_text`` 口径一致，
    两条通道的结果文本因此长得一样（引用解析只认这一份文本）。

    解不动不抛：工具结果决定「律师能不能看到检索证据」，一条怪形状的结果不该让
    整轮事件流崩掉，所以未知类型退化成空串而不是异常。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _translate_usage(data: dict[str, Any]) -> list[dict[str, Any]]:
    """``assistant/message`` 的 ``data.usage`` → ``usage`` 帧。

    实测每次模型调用（= 一个 ``step``）的 ``assistant/message`` 都带一份，
    形状固定为 ``{inputTokens, outputTokens, totalTokens, cacheReadTokens}``：

    - ``inputTokens`` 是**未命中缓存**的 prompt token，``cacheReadTokens`` 是
      命中的那部分（实测 ``242 + 10944 + 162 == 11348 == totalTokens``）；
      正因为 ``inputTokens`` 不含缓存命中，才能逐字映到 ``UsageEvent`` 的
      ``input_tokens``（它同样只装未命中部分，见 ``sse_types.UsageEvent``）。
    - ``totalTokens`` **不是**本轮总量，是**累加后的上下文大小**（实测同一轮
      由 11348 涨到 38986）——拿它当用量会把成本算成几倍，所以直接丢掉，
      只累加 ``inputTokens`` / ``outputTokens`` / ``cacheReadTokens``。
    - 没有 ``cacheWriteTokens`` 字段：``cache_write_tokens`` 恒 0（dsh 侧不
      上报，编一个数会让“缓存命中率”失真）。

    一轮里工具循环有多个 step，编排层 ``stream.py`` 按帧累加（与 pi 同口径），
    所以这里**逐次发**而不是攒一帧。三项全 0 时不发帧：那是“没拿到统计”，
    发出去会变成“这轮不花钱”。
    """
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return []

    def _count(key: str) -> int:
        value = raw.get(key)
        # bool 是 int 的子类，``True`` 不该被当成 1 token。
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0
        return max(0, int(value))

    input_tokens = _count("inputTokens")
    output_tokens = _count("outputTokens")
    cache_read_tokens = _count("cacheReadTokens")
    if not (input_tokens or output_tokens or cache_read_tokens):
        return []
    return [
        {
            "type": "usage",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": 0,
        }
    ]


def _translate_assistant_message(data: dict[str, Any]) -> list[dict[str, Any]]:
    """``assistant/message`` → ``thinking`` / ``delta`` / ``tool_call`` / ``usage``。

    字段形状照 ``api.py`` 的 ``final_response``：

    ::

        data["message"]["content"] = [
            {"type": "text", "text": "..."},
            {"type": "thinking", "text": "..."},        # 思考块（推断）
            {"type": "tool-call", ...},                 # 工具调用（确认过的真名）
        ]

    ``final_response`` 里的 ``content_owner = message if isinstance(message, dict)
    else data``，说明两种形状都可能出现（有 ``message`` 包装 / 无包装）。
    这里同样两路都认。

    工具块的真名是 **``tool-call``（连字符）**，见 SDK ``packages/llm/src/
    types.ts`` 与 ``assembler.ts``；字段是 ``callId`` / ``name`` / ``arguments``
    （与 run 事件 ``tool/call`` 同名）。camelCase ``toolCall`` / 下划线
    ``tool_call`` 是早期推断名（真实流里没出现过），按 ``id`` / ``name`` 认——
    只认前两个名字的版本曾让 dsh **一帧 ``tool_call`` 都不产**，前端看不到工具名
    与参数。思考块的类型名仍是推断（``final_response`` 只处理 text 块）。

    缺 ``callId``/``id`` 或 ``name`` 的块跳过：``tool_call_id`` 是前端归并
    请求与结果的键（前端 ``applyToolResult`` 按它匹配），空 id 会配错行。

    用量不在这里取：它不在 ``message`` 里，而在**同一个 event 的** ``data.usage``
    上（只挂在事件外层）。所以内容块无论能不能认出，都照样补一帧 ``usage``
    （见 :meth:`_translate_usage`）——“只认识内容块就把用量也吞掉”会让一个新
    块类型顺手弄丢整轮成本。
    """
    message = data.get("message") if isinstance(data.get("message"), dict) else data
    content = (message or {}).get("content")
    if not isinstance(content, list):
        return _translate_usage(data)
    frames: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                frames.append({"type": "delta", "content": text})
        elif block_type in ("thinking", "reasoning"):
            text = block.get("text") or block.get("thinking")
            if isinstance(text, str) and text:
                frames.append({"type": "thinking", "content": text})
        elif block_type in ("tool-call", "toolCall", "tool_call"):
            call_id = str(block.get("callId") or block.get("id") or block.get("toolCallId") or "")
            name = str(block.get("name") or block.get("toolName") or "")
            if call_id and name:
                args = block.get("arguments") or block.get("args")
                frames.append(
                    {
                        "type": "tool_call",
                        "tool_call_id": call_id,
                        "name": name,
                        "arguments": _tool_call_arguments(args),
                    }
                )
    frames.extend(_translate_usage(data))
    return frames
