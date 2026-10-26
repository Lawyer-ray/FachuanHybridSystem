"""让模型主动向律师澄清 —— ``ask_user``。

## 为什么需要这个工具

法穿此前只有「要不要执行」的审批，**没有「你要选哪个」**。律师说
「帮我处理这个案子」，同时缺三个关键信息（哪个当事人、适用哪版模板、
管辖地选哪个）时，模型只有两条路：

1. 瞎猜 → 做错返工，且错得很自信；
2. 写一堆「如果您指的是 A，则…；如果是 B，则…」的空话 → 用户还得再问一遍。

``ask_user`` 给出第三条：一次性问清 2–4 个互相独立的问题，带选项、允许
自由回答、允许附言，答完继续干。

## 它不是审批

| | 审批（approval） | 提问（ask_user） |
|:-|:-|:-|
| 超时 | 拒绝（fail-closed） | **交回模型按假设继续**，不阻断 |
| 目的 | 拦危险操作 | 补缺失信息 |
| 回答 | 布尔 | 结构化数据 |

所以本工具**不进审批分级**（`approval-gate.ts` 把它归为低风险直通），
也不该把任务挂死：律师没答就问不到，模型自己说明假设继续。

## 一次只问互相独立的

有依赖关系的问题必须分批：先问「哪个当事人」，拿到答案才可能知道
「适用哪份模板」。一次塞进去只会让律师面对一堆他还没法回答的问题。
"""

from __future__ import annotations

from typing import Any

from mcp_server.identity import current_session_id

#: 工具结果的 hint 会直接进模型上下文，语气要对模型说话（而不是对用户）


async def ask_user(
    questions: list[dict[str, Any]],
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """向律师提问并等待回答（一次最多 4 个互相独立的问题）。

    **什么时候该用它**（缺一不可）：

    1. 缺的信息**无法**从工具查到（能查到的一律先查——猜用户身份、
       猜当前时间是禁止的，那些有专门的工具）；
    2. 猜错的代价明显高于问一句（选错当事人、选错模板、选错管辖地）；
    3. 问题**互相独立**（有依赖的必须分批问）。

    **什么时候不该用**：

    - 能从 `list_*` / `get_*` 查到的（先查再说）；
    - 纯风格偏好（那种用 `remember` 记偏好，不必每次问）；
    - 律师已经明确说「你看着办」的时候（那就按最佳判断做，别回头问）。

    Args:
        questions: 问题数组，每项支持：
            - ``question``（必填）：问题正文，一句话说清要什么；
            - ``options``：选项数组。字符串或 ``{label, description}``；
            - ``context``：折叠显示的补充说明（为什么问这个）；
            - ``allow_freeform``：是否允许自由输入（默认 True）；
            - ``allow_multiple``：是否多选（默认 False）；
            - ``allow_comment``：是否允许在选项外补一句（默认 False）。
        timeout_seconds: 等待上限，默认 180 秒。律师在忙时不必干等。

    Returns:
        ``{"status": ..., "questions": [...]}``：

        - ``answered``：拿到回答，``questions[].selections`` / ``text`` /
          ``comment`` 里有内容；
        - ``skipped``：律师主动跳过，或全部未答；
        - ``timed_out``：等超时；
        - ``no_channel``：当前没有可回答的界面（任务式后台运行）。

        **后三种都不是错误**：此时按现有信息继续，并**明确说明你假定了什么**。
        绝不能把「没问到」当成「可以随便编」。
    """
    from apps.agent.services.question import DEFAULT_QUESTION_TIMEOUT
    from apps.agent.services.question import ask_user as service

    # 用户在工具参数里可以指定更短/更长的等待，但不允许无限等——
    # 每个等待都占着一个进程池槽位，等太久会让别人排队。
    effective_timeout = float(timeout_seconds) if timeout_seconds > 0 else DEFAULT_QUESTION_TIMEOUT
    effective_timeout = min(max(effective_timeout, 10.0), 600.0)

    result = await service(
        questions=questions,
        session_id=current_session_id() or None,
        timeout=effective_timeout,
    )
    if result.get("status") == "answered":
        answered = sum(1 for q in result.get("questions", []) if q.get("status") == "answered")
        result["summary"] = f"律师回答了 {answered}/{len(result.get('questions', []))} 个问题"
    return result
