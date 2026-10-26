"""Agent 提问服务 —— 模型挂起等律师澄清。

## 与审批的本质区别

审批是**闸门**（超时 = 拒绝，fail-closed）；提问是**求助**（超时 = 交回模型
自己决定，不阻断）。把提问做成 fail-closed 会让「律师正忙」变成「任务失败」，
这是把产品缺陷当成安全特性。

所以这里的超时语义是：返回 ``timed_out``，模型按现有信息继续**并显式声明
假设**。AGENTS.md 里「缺料不许猜、要说明假设」那条由此才真正可执行。

## 跨 worker

与审批同构：
- 状态真相在数据库（``AgentQuestion``）
- 答案经 Redis 传递（SSE 连接在 worker A，回答 POST 可能落到 worker B）
- 进程内 ``asyncio.Event`` 只做同 worker 快路径

## 为什么答案要校验 id 对齐

批量提问时前端可能只答一部分、或顺序错乱。答案按 ``id`` 回填而不是按下标，
避免「答的是第 2 题、被当成第 1 题」这种静默错位——法律场景里问错一次
比不问更糟。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from django.core.cache import cache
from django.utils import timezone

from ..models import AgentQuestion, AgentSession
from .event_bus import redis_cache_enabled

logger = logging.getLogger(__name__)

#: 答案在 Redis 的键前缀（跨 worker 传递）
ANSWER_KEY_PREFIX = "agent:question:answer:"
#: 答案 TTL：与最大等待时长同量级，够跨 worker 取到即可
ANSWER_TTL = 600

#: 一次提问的默认等待上限。比审批短——律师在页面上看到问题会立刻答，
#: 拖着不答就是不想答，等太久只会让任务白占一个进程池槽位。
DEFAULT_QUESTION_TIMEOUT = 180.0
#: 单个问题的上限（防止模型一次问 20 个把人淹了）
MAX_QUESTIONS = 4


class _QuestionWaiter:
    """进程内等待器：把「前端答了什么」交回阻塞的调用方。"""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._results: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def register(self, question_id: str) -> asyncio.Event:
        async with self._lock:
            event = asyncio.Event()
            self._events[question_id] = event
            self._results[question_id] = None
            return event

    async def resolve(self, question_id: str, answers: list[dict[str, Any]], skipped: bool) -> bool:
        """前端回答后调用；返回是否找到等待者。"""
        async with self._lock:
            event = self._events.get(question_id)
            if event is None:
                return False
            self._results[question_id] = {"answers": answers, "skipped": skipped}
            event.set()
            return True

    async def take_result(self, question_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._results.get(question_id)

    async def discard(self, question_id: str) -> None:
        async with self._lock:
            self._events.pop(question_id, None)
            self._results.pop(question_id, None)


_waiter = _QuestionWaiter()


def _write_answer(question_id: str, answers: list[dict[str, Any]], skipped: bool) -> None:
    """把答案写进 Redis（跨 worker 共享）。"""
    if not redis_cache_enabled():
        return
    import json

    try:
        cache.set(
            f"{ANSWER_KEY_PREFIX}{question_id}",
            json.dumps({"answers": answers, "skipped": skipped}, ensure_ascii=False),
            ANSWER_TTL,
        )
    except Exception:
        logger.warning("写问题答案失败（跨 worker 将收不到）: %s", question_id, exc_info=True)


def _read_answer(question_id: str) -> dict[str, Any] | None:
    """读其他 worker 写入的答案。"""
    if not redis_cache_enabled():
        return None
    import json

    try:
        raw = cache.get(f"{ANSWER_KEY_PREFIX}{question_id}")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except (TypeError, ValueError):
        return None


def _clear_answer(question_id: str) -> None:
    if not redis_cache_enabled():
        return
    try:
        cache.delete(f"{ANSWER_KEY_PREFIX}{question_id}")
    except Exception:
        pass


async def get_question_by_id(question_id: str) -> Any:
    """按 question_id 取提问记录（带 session）；不存在返回 None。

    放在 service 层：结构门禁要求 apps/*/api/ 不直连 ORM。
    """
    from apps.agent.models.question import AgentQuestion

    return await AgentQuestion.objects.filter(question_id=question_id).select_related("session").afirst()


async def list_pending_questions_for_user(user_id: int, limit: int = 20) -> list[Any]:
    """某用户待回答的提问（最新在前，最多 limit 条）。"""
    from apps.agent.models.question import AgentQuestion

    return [
        row
        async for row in AgentQuestion.objects.filter(
            user_id=user_id, status=AgentQuestion.Status.PENDING
        ).select_related("session")[:limit]
    ]


def normalize_questions(raw: Any) -> list[dict[str, Any]]:
    """校验并归一化模型提交的问题列表。

    宽容解析的理由：国产模型对 JSON schema 的遵循度参差，常见的是
    ``{"questions": [...]}`` 与直接 ``[...]`` 两种形态，以及把 options 写成
    字符串数组而不是对象数组。与其让工具调用失败，不如归一化后接受——
    这里没有安全风险（提问本身无副作用），只有体验差别。

    Raises:
        ValueError: 完全无法解析，或问题数为 0/超上限。
    """
    if isinstance(raw, dict):
        raw = raw.get("questions")
    if not isinstance(raw, list):
        raise ValueError("questions 必须是数组")
    if not raw:
        raise ValueError("至少要问一个问题")
    if len(raw) > MAX_QUESTIONS:
        raise ValueError(f"一次最多问 {MAX_QUESTIONS} 个问题（收到 {len(raw)} 个）；有依赖关系的请分批问")

    out: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if isinstance(item, str):
            item = {"question": item}
        if not isinstance(item, dict):
            raise ValueError(f"第 {idx + 1} 个问题格式不对")
        text = str(item.get("question") or item.get("q") or "").strip()
        if not text:
            raise ValueError(f"第 {idx + 1} 个问题缺少 question 文本")

        raw_options = item.get("options") or []
        options: list[dict[str, str]] = []
        if isinstance(raw_options, list):
            for opt in raw_options:
                if isinstance(opt, str):
                    options.append({"label": opt, "description": ""})
                elif isinstance(opt, dict):
                    label = str(opt.get("label") or opt.get("text") or opt.get("value") or "").strip()
                    if label:
                        options.append({"label": label, "description": str(opt.get("description") or "")})

        out.append(
            {
                # id 由服务端定：模型给的 id 可能重复，而答案要靠它对齐
                "id": str(item.get("id") or f"q{idx + 1}"),
                "question": text,
                "context": str(item.get("context") or ""),
                "options": options,
                "allow_freeform": bool(item.get("allow_freeform", True)),
                "allow_multiple": bool(item.get("allow_multiple", False)),
                "allow_comment": bool(item.get("allow_comment", False)),
            }
        )
    return out


def _merge_answers(questions: list[dict[str, Any]], answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把答案按 id 回填到问题上，缺的标 ``unanswered``。

    为什么按 id 而不是下标：前端可能只答一部分，或顺序错乱。按 id 对齐
    才不会出现「答的是第 2 题被当成第 1 题」的静默错位。
    """
    by_id = {str(a.get("id")): a for a in answers if isinstance(a, dict)}
    merged: list[dict[str, Any]] = []
    for q in questions:
        hit = by_id.get(q["id"])
        if hit is None:
            merged.append({**q, "status": "unanswered"})
            continue
        merged.append(
            {
                **q,
                "status": "answered",
                "selections": hit.get("selections") or [],
                "text": str(hit.get("text") or ""),
                "comment": str(hit.get("comment") or ""),
            }
        )
    return merged


async def ask_user(
    *,
    questions: Any,
    user_id: int | None = None,
    session_id: str | None = None,
    timeout: float = DEFAULT_QUESTION_TIMEOUT,
) -> dict[str, Any]:
    """向律师提问并阻塞等待回答。

    Returns:
        ``{"status": "answered"|"timed_out"|"no_channel"|"skipped", "questions": [...]}``

    调用方（MCP 工具）应把整个返回值交给模型，而不是只取答案正文——
        ``timed_out`` / ``skipped`` 这些状态本身是重要信号：模型据此决定
        「按假设继续」还是「就此停下等律师」。
    """
    normalized = normalize_questions(questions)
    question_id = uuid.uuid4().hex

    session = None
    if session_id:
        try:
            session = await AgentSession.objects.filter(session_id=session_id).afirst()
        except Exception:
            logger.warning("按 session_id 查会话失败（提问记录将缺会话关联）: %s", session_id, exc_info=True)

    record = await AgentQuestion.objects.acreate(
        question_id=uuid.UUID(question_id),
        session=session,
        user_id=user_id,
        questions=normalized,
    )

    # 登记等待者必须在 publish 之前（同审批的反向顺序会导致「已答但等不到」）
    event: asyncio.Event | None = None
    delivered = 0
    has_remote = False
    if session_id:
        event = await _waiter.register(question_id)
        from .event_bus import get_bus

        bus = get_bus()
        has_remote = bool(await bus.has_subscribers(session_id)) or redis_cache_enabled()
        delivered = await bus.publish(
            session_id,
            {
                "type": "question_request",
                "question_id": question_id,
                "questions": normalized,
                "timeout_seconds": int(timeout),
            },
        )

    # 没有可送达的通道（任务式后台 / 律师没开页面）：
    # 不阻塞、不报错，直接告诉模型「问不到」，让它按假设继续。
    # 这与审批的「挂起等离线决定」刻意不同——提问不是闸门，不该把任务挂死。
    if event is None or not (delivered or has_remote):
        record.status = AgentQuestion.Status.TIMED_OUT
        record.answered_at = timezone.now()
        await record.asave(update_fields=["status", "answered_at"])
        logger.info("提问无接收通道，立即返回 timed_out: %s", question_id)
        return {
            "status": "no_channel",
            "hint": "当前没有可回答的界面（律师未打开会话页面）。请基于现有信息继续，并明确说明你做了哪些假设。",
            "questions": _merge_answers(normalized, []),
        }

    try:
        payload = await _wait_answer(question_id, event, timeout)
    except TimeoutError:
        record.status = AgentQuestion.Status.TIMED_OUT
        record.answered_at = timezone.now()
        await record.asave(update_fields=["status", "answered_at"])
        logger.info("提问超时: %s", question_id)
        return {
            "status": "timed_out",
            "hint": "律师没有在时限内回答（可能在忙）。请基于现有信息继续，并明确列出你假定了什么。",
            "questions": _merge_answers(normalized, []),
        }
    finally:
        await _waiter.discard(question_id)
        _clear_answer(question_id)

    answers = list(payload.get("answers") or [])
    skipped = bool(payload.get("skipped"))
    record.answers = answers
    record.skipped = skipped
    record.status = AgentQuestion.Status.ANSWERED
    record.answered_at = timezone.now()
    await record.asave(update_fields=["answers", "skipped", "status", "answered_at"])

    merged = _merge_answers(normalized, answers)
    answered = [q for q in merged if q["status"] == "answered"]
    if skipped or not answered:
        return {
            "status": "skipped",
            "hint": "律师跳过了提问（不想答/答不了）。请继续，但要把未知项显式标成假设。",
            "questions": merged,
        }
    return {"status": "answered", "questions": merged}


async def _wait_answer(question_id: str, event: asyncio.Event, timeout: float) -> dict[str, Any]:
    """等待答案：本进程快路径 + Redis 跨进程轮询。

    使用 ``asyncio.wait_for`` 包住而不是裸 ``event.wait()``——超时必须能
    打断等待，否则池槽位会被永久占用。
    """

    async def _poll() -> dict[str, Any]:
        # 先查一次：可能答案比 register 更早到（前端重试/自动回答）
        remote = _read_answer(question_id)
        if remote is not None:
            return remote
        while True:
            await event.wait()
            local = await _waiter.take_result(question_id)
            if local is not None:
                return local
            remote = _read_answer(question_id)
            if remote is not None:
                return remote
            # 事件被 set 但两边都没结果：等下一轮（不把 None 当成答案）
            event.clear()

    return await asyncio.wait_for(_poll(), timeout=timeout)


async def submit_answer(
    *,
    question_id: str,
    answers: list[dict[str, Any]],
    skipped: bool = False,
) -> bool:
    """前端提交回答（HTTP 端点调用）。

    Returns:
        是否找到等待中的调用方。``False`` 意味着等待进程已不在（超时/进程重启），
        答案仍会写 Redis 与数据库，但没人会读到——调用方应据此提示用户。
    """
    found = await _waiter.resolve(question_id, answers, skipped)
    _write_answer(question_id, answers, skipped)

    # 有等待者时它是真相来源；没有时仍然落库，便于审计「律师当时答了什么」
    try:
        record = await AgentQuestion.objects.filter(question_id=uuid.UUID(question_id)).afirst()
    except (ValueError, AttributeError):
        return found
    if record is None or record.status != AgentQuestion.Status.PENDING:
        return found
    if not found:
        # 等待方已消失（超时）：只补记录，不改 status 为 answered 以免误导
        return False
    return found
