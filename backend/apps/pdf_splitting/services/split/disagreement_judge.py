"""多引擎分歧的第三方打分裁定器：把一个字段的多条 OCR 候选交给判别式打分器相对比较。

## 它解决的问题

两个 OCR 引擎读同一处得出不同文本时，谁对？本模块把**同一条候选文本**连同**该页原图**
发给判别式打分器 ``MiniCPM-OCR-Jev``（``api.modelbest.cn``，OpenAI 兼容
``/v1/chat/completions``，请求体走 ``minicpm_ocr_jev.mode="score"``），拿到「这段文字与
图上文字相符」的概率 ``prob_yes``，再用**相对比较**决定「自动采信」还是「交人工」。

## 四条实测约束（本文件每个设计选择都由它们决定）

1. **并发 > 2 立刻 429**（``{"error":{"code":"rate_limit_exceeded"}}``）。所以进程内有一个
   全局并发闸门、硬上限 2（:data:`_HARD_CONCURRENCY_CAP`），429 / 5xx / 网络异常退避重试。
2. **真实证件图在可读分辨率下返回 HTTP 400 ``content_policy_violation``**。重试必然还是拒，
   所以**不可重试**：该候选直接标 ``policy_rejected``，整次判定交人工；另外
   :data:`BLOCKED_DOMAINS` 里的证件/账号类字段整体挡在请求之外，一次 HTTP 都不发。
3. **``prob_yes`` 的绝对值不可作阈值**：同一批真实卷宗里，真值的绝对分可能 0.158 也可能
   0.996（同一模型、同一批图）。任何绝对阈值都会在低分段把真值误杀，所以只做相对比较：
   胜者分 / 次高分 ≥ ``OCR_JUDGE_RATIO_MIN``（默认 10）。
4. **错值也可能拿 0.58**（汉字形近字，如「张三丰 / 张四丰」）。比率大但两边分都低时，
   说明模型对这一段本来就没把握，所以另加最低胜者分 ``OCR_JUDGE_PROB_FLOOR``（默认 0.05）。

口径来源：``docs/analysis/multi-engine-ocr-brief-2026-11-25.md`` §10（三轮复审）与
``dual_engine.py`` 的模块注释（「一致 ≠ 正确，分歧才是可靠信号」）。

## 与「投票」的区别

本模块**不投票**：它只在一条候选文本上问「这段文字和图对得上吗」，再看两条候选的
**相对**置信度是否拉得足够开。票数、多数派都不参与——两引擎一致地错是最常见的静默错误。

## 契约

:func:`judge_candidates` 的返回结构与 ``reason`` 取值集合被下游（字段校验 / 人工抽屉）
依赖；改字段名或加取值必须同步下游。

## 隐私

候选文本是卷宗里的姓名 / 证件号 / 金额，**禁止整段进日志**：:func:`_mask` 只留前 8 个
字符 + 总长度（不超过 8 个字符时一个字符都不留），:func:`snapshot` 同口径。
"""

from __future__ import annotations

import base64
import json
import logging
import math
import random
import threading
import time
from collections import deque
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from apps.core.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)

#: 普通文本字段的域标识。``BLOCKED_DOMAINS`` 之外的域才允许送给打分器。
DOMAIN_TEXT = "text"

#: 证件 / 账号类字段的域标识集合：这些字段一律不送打分器。
#:
#: 实测真实证件图在可读分辨率下必被 ``content_policy_violation`` 拒绝（还白占一次全局
#: 并发额度，把其它判定排队）。这几类字段的正确性本来也不该靠模型打分，而是靠确定性校验
#: （身份证 Mod-11 / USCC Mod-31 / Luhn），见简报 §10.4 的 L1 校验和。
BLOCKED_DOMAINS: frozenset[str] = frozenset({"id_card", "uscc", "bank_card", "account_no"})

# ── 只有两项走 SystemConfig，其余全是模块常量 ────────────────────────────────
#
# 判据：**因部署而异**的才进配置表（key、开关）；**实测出来的工程常数**留在代码里。
# 后者写进 admin 只会给「有人随手调一下」开门，而且调坏了是静默的——阈值调松了不会报错，
# 只会把更多错值采信成对的。仓库里同一个口径的例子：``credential_pool._COOLDOWN_SECONDS``、
# ``wholebook_segment_detector._TOTAL_CHAR_BUDGET``、``cloud_batch.DEFAULT_BATCH_PAGES``。
OCR_JUDGE_ENABLED_KEY = "OCR_JUDGE_ENABLED"
OCR_JUDGE_API_KEY_KEY = "OCR_JUDGE_API_KEY"  # pragma: allowlist secret —— 这是配置键名，不是密钥本身

#: 接口地址与模型名是**契约的一部分**：换模型意味着请求体里的 ``minicpm_ocr_jev`` 字段
#: 语义也要跟着变，那不是改一个字符串能改的。所以写死。
JUDGE_API_URL = "https://api.modelbest.cn/v1/chat/completions"
JUDGE_MODEL = "MiniCPM-OCR-Jev"

#: 进程内并发上限。实测 4 并发**立即 429**、2 稳定——这是供应商侧的硬墙，不是
#: 「调大提速」的性能参数，因此不给配置项（``_HARD_CONCURRENCY_CAP`` 保持同值）。
JUDGE_MAX_CONCURRENCY = 2

#: 单次请求超时。实测中位 1.2s、最慢 10.03s，留足余量给拥塞。
JUDGE_TIMEOUT_SECONDS = 180.0

#: 相对倍数下限：胜者分 / 次高分。实测真错案例 55–1900 倍；汉字形近字的错值能拿 0.58
#: （真值 0.994，仅 1.7 倍），定低了会把形近字误采信。
JUDGE_RATIO_MIN = 10.0

#: 胜者最低分。实测真值分数可以是 0.158（模糊证件块）——绝对值不可比，只作下限兜底，
#: 不拿来当主判据。
JUDGE_PROB_FLOOR = 0.05

#: 只有这两个键可能出现在 SystemConfig 里；键 → 「库里没有」时的默认值。
_CONFIG_DEFAULTS: dict[str, str] = {
    OCR_JUDGE_ENABLED_KEY: "0",
    OCR_JUDGE_API_KEY_KEY: "",
}

# ── 判定取值（下游依赖，改名字必须同步调用方）────────────────────────────────
VERDICT_SCORED = "scored"
VERDICT_POLICY_REJECTED = "policy_rejected"
VERDICT_FAILED = "failed"

DECISION_ACCEPT = "accept"
DECISION_HUMAN = "human"

REASON_IDENTICAL = "identical"
REASON_DOMAIN_BLOCKED = "domain_blocked"
REASON_RATIO_OK = "ratio_ok"
REASON_RATIO_LOW = "ratio_low"
REASON_PROB_LOW = "prob_low"
REASON_POLICY_REJECTED = "policy_rejected"
REASON_CALL_FAILED = "call_failed"
REASON_DISABLED = "disabled"

# ── 传输参数（每条都有实测来源，别凭感觉调）───────────────────────────────────
#: 实测并发 > 2 立刻 429；配置项只能在这个硬上限以内往下调。
_HARD_CONCURRENCY_CAP = 2

#: 退避 0.5s → 1s → 2s（加抖动），即首次 + 最多 3 次重试。
_MAX_RETRIES = 3
_MAX_ATTEMPTS = _MAX_RETRIES + 1
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_MAX_SECONDS = 2.0
_BACKOFF_JITTER_RATIO = 0.25
#: 单次判定的退避总预算（0.5 + 1 + 2 = 3.5s）；抖动也吃这份预算，不额外累加。
_BACKOFF_TOTAL_CAP_SECONDS = 3.5

_RATE_LIMITED_STATUS = 429
_SERVER_ERROR_STATUS = 500
_BAD_REQUEST_STATUS = 400
_AUTH_FAILED_STATUSES = frozenset({401, 403})
#: 上游策略拒绝的错误码：命中即判「不可重试」。
_POLICY_VIOLATION_CODE = "content_policy_violation"

_MODE_SCORE = "score"
_RATIO_EPSILON = 1e-9
_MASK_HEAD_CHARS = 8
_MAX_DETAIL_CHARS = 120

#: ``snapshot()`` 环形缓冲的默认容量。
_SNAPSHOT_MAX = 50

#: fail-open 兜底收的异常类型（**故意不写裸 ``except Exception``**：pre-commit 的
#: broad-except 棘轮只许下调）。列出的这些都实测会从这条链上冒出来：
#: ``httpx.HTTPError`` 传输层、``OSError`` socket、``ValueError`` 含 JSON 解码、
#: ``TypeError``/``AttributeError`` 上游字段类型不符、``KeyError``/``IndexError``
#: 响应结构不符、``RuntimeError`` 是 pytest-django 拒绝无库访问的形态。
_FAIL_OPEN_ERRORS = (
    httpx.HTTPError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    KeyError,
    IndexError,
    AttributeError,
)


@dataclass(frozen=True)
class CandidateScore:
    """一条候选文本的打分结果。

    Attributes:
        text: 候选原文（**只回给调用方，不进日志**）。
        prob_yes: 「这段文字与图上文字相符」的概率；``verdict`` 不是 ``scored`` 时必为 ``None``。
        verdict: ``scored`` | ``policy_rejected`` | ``failed``。
        detail: 机器可读的失败原因（``http_400`` / ``transport:ConnectError`` / ``bad_json`` …）。
            刻意只放错误码与类型名、不回显响应体：响应体可能带候选原文。
    """

    text: str
    prob_yes: float | None
    verdict: str
    detail: str = ""


@dataclass(frozen=True)
class Judgement:
    """一次判定的结论。

    Attributes:
        decision: ``accept``（自动采信 ``winner``）| ``human``（交人工）。
        winner: 采信的候选原文；``decision="human"`` 时为 ``None``。
        scores: 实际发出的打分结果（未发请求的路径——``disabled`` / ``domain_blocked`` /
            ``identical``——为空元组）。
        reason: 判定依据，取值见 ``REASON_*``。
        ratio: 胜者分 / 次高分；只在真的算过比率（规则 6 之后）时有值，便于人工抽屉展示。
    """

    decision: str
    winner: str | None
    scores: tuple[CandidateScore, ...]
    reason: str
    ratio: float | None = None


@dataclass(frozen=True)
class _Settings:
    """一次判定用的配置快照（每次判定现读一遍，线上改配置即时生效）。"""

    enabled: bool
    api_key: str


@dataclass(frozen=True)
class _ScoreResult:
    """一次候选打分：结论 + 该次请求的 token 用量（实测 ``completion_tokens`` 恒为 0）。"""

    score: CandidateScore
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class _Attempt:
    """单次 HTTP 尝试的结论：``result`` 非空即终局，否则 ``detail`` 说明为何可重试。"""

    result: _ScoreResult | None
    detail: str = ""


class _ConcurrencyGate:
    """进程内全局并发闸门（模块级单例 :data:`_GATE`，跨调用方共享）。

    实测并发 > 2 立刻 429，所以硬上限 2；``OCR_JUDGE_MAX_CONCURRENCY`` 只能在上限以内
    往下调（例如线上想给别的任务让路），往上调无效——那不是「更激进」，是「必然 429」。
    """

    def __init__(self, *, hard_cap: int) -> None:
        self._hard_cap = max(1, int(hard_cap))
        self._condition = threading.Condition()
        self._in_flight = 0
        self._limit = self._hard_cap

    @contextmanager
    def slot(self, limit: int) -> Iterator[None]:
        """占一个并发位；``limit`` 取配置值与硬上限的较小者（下限 1）。"""
        effective = max(1, min(int(limit), self._hard_cap))
        with self._condition:
            self._limit = effective
            while self._in_flight >= self._limit:
                self._condition.wait()
            self._in_flight += 1
        try:
            yield
        finally:
            with self._condition:
                self._in_flight -= 1
                self._condition.notify()


_GATE = _ConcurrencyGate(hard_cap=_HARD_CONCURRENCY_CAP)

#: 最近的判定留痕（环形缓冲）。只存掩码文本，见 :func:`_record`。
_SNAPSHOTS: deque[dict[str, Any]] = deque(maxlen=_SNAPSHOT_MAX)
_SNAPSHOTS_LOCK = threading.Lock()


def judge_candidates(image_bytes: bytes, candidates: Sequence[str], *, domain: str = DOMAIN_TEXT) -> Judgement:
    """裁定多条 OCR 候选文本里哪一条与 ``image_bytes`` 上的文字相符。

    决策顺序固定（依据写在各分支与 :func:`_decide` 的注释里）：

    1. 未启用（``OCR_JUDGE_ENABLED`` 默认 ``"0"``）→ ``human / disabled``；
    2. ``domain in BLOCKED_DOMAINS`` → ``human / domain_blocked``，**一次 HTTP 都不发**；
    3. 去重后只剩一条 → ``accept / identical``（没有分歧可判，也省掉请求）；
    4. 任一候选被策略拒绝 → ``human / policy_rejected``；
    5. 任一候选调用失败 → ``human / call_failed``；
    6. 取 ``prob_yes`` 最高者为胜者，``ratio = 胜者分 / max(次高分, 1e-9)``；
    7. 胜者分 < ``OCR_JUDGE_PROB_FLOOR`` → ``human / prob_low``；
    8. ``ratio`` < ``OCR_JUDGE_RATIO_MIN`` → ``human / ratio_low``；
    9. 否则 ``accept / ratio_ok``。

    Args:
        image_bytes: 该字段所在页的 **PNG** 图像字节（请求体按实测口径声明 ``image/png``）。
        candidates: 至少两条候选文本（同一字段被不同引擎/不同路径读出的结果）。
        domain: 字段域；证件与账号类字段见 :data:`BLOCKED_DOMAINS`。

    Returns:
        :class:`Judgement`。本函数**永不抛**：任何意外都落到 ``human / call_failed``。
    """
    started = time.monotonic()
    try:
        return _judge(image_bytes=image_bytes, candidates=candidates, domain=domain, started=started)
    except _FAIL_OPEN_ERRORS as exc:
        # fail-open：打分只是「分歧时多一票参考」，不许因为它把上传/分段主链拖挂。
        logger.warning(
            "ocr_disagreement_judge_unexpected_error",
            extra={"domain": domain, "error_type": type(exc).__name__},
        )
        return _record(
            Judgement(decision=DECISION_HUMAN, winner=None, scores=(), reason=REASON_CALL_FAILED),
            domain=domain,
            started=started,
        )


def _judge(*, image_bytes: bytes, candidates: Sequence[str], domain: str, started: float) -> Judgement:
    settings = _load_settings()
    if not settings.enabled:
        # 规则 1：默认关闭。关着时与引入本模块前逐位一致——分歧只进人工抽屉，不产生任何
        # 自动采信；打开前必须先有「分歧进人工」的实测分歧率（简报 §10.2）。
        return _record(
            Judgement(decision=DECISION_HUMAN, winner=None, scores=(), reason=REASON_DISABLED),
            domain=domain,
            started=started,
        )

    if domain in BLOCKED_DOMAINS:
        # 规则 2：证件/账号类字段一次请求都不发。实测这类图必被 content_policy_violation
        # 拒绝（白等一个 180s 超时 + 白占并发额度），且它们的正确性靠确定性校验，
        # 不靠模型打分（简报 §10.4 的 L1 校验和）。
        return _record(
            Judgement(decision=DECISION_HUMAN, winner=None, scores=(), reason=REASON_DOMAIN_BLOCKED),
            domain=domain,
            started=started,
        )

    distinct = _distinct_candidates(candidates)
    if len(distinct) == 1:
        # 规则 3：去重后只剩一条 → 没有分歧可言，直接采信（顺带省掉两次请求）。
        return _record(
            Judgement(decision=DECISION_ACCEPT, winner=distinct[0], scores=(), reason=REASON_IDENTICAL),
            domain=domain,
            started=started,
        )

    if not distinct:
        # 空候选（或全空白）：没有任何可判文本。``reason`` 只有 8 个合法取值，这里归到
        # ``call_failed``——它的语义是「判定没做成 → 交人工」，不会让上层误以为量到了什么。
        return _record(
            Judgement(decision=DECISION_HUMAN, winner=None, scores=(), reason=REASON_CALL_FAILED),
            domain=domain,
            started=started,
        )

    results = _score_all(settings=settings, image_data_url=_data_url(image_bytes), texts=distinct)
    judgement = _decide(
        scores=tuple(result.score for result in results),
        ratio_min=JUDGE_RATIO_MIN,
        prob_floor=JUDGE_PROB_FLOOR,
    )
    return _record(
        judgement,
        domain=domain,
        started=started,
        prompt_tokens=sum(result.prompt_tokens for result in results),
        completion_tokens=sum(result.completion_tokens for result in results),
    )


def _decide(*, scores: tuple[CandidateScore, ...], ratio_min: float, prob_floor: float) -> Judgement:
    """规则 4–9：从打分结果得出结论（纯函数，不发请求）。

    调用方保证 ``scores`` 至少两条且每条都能落到 ``scored``（否则在前两条规则就返回了）。
    """
    if any(score.verdict == VERDICT_POLICY_REJECTED for score in scores):
        # 规则 4：策略拒绝说明「这一页/这个字段根本不许模型看」，重试必然还拒；也不能因为
        # 另一条候选分高就采信——缺一边的对照，比率没有意义。
        return Judgement(decision=DECISION_HUMAN, winner=None, scores=scores, reason=REASON_POLICY_REJECTED)

    if any(score.verdict == VERDICT_FAILED for score in scores):
        # 规则 5：任何一条候选没拿到分（401/403、退避耗尽、响应结构不符），比率就是残缺的。
        return Judgement(decision=DECISION_HUMAN, winner=None, scores=scores, reason=REASON_CALL_FAILED)

    ranked = sorted(scores, key=_prob_of, reverse=True)
    best = ranked[0]
    best_prob = _prob_of(best)
    # 规则 6：相对比较。分母兜 1e-9 是为了「次高分恰为 0」时不开除零，且比率为正。
    ratio = best_prob / max(_prob_of(ranked[1]), _RATIO_EPSILON)

    if best_prob < prob_floor:
        # 规则 7：胜者分低于下限。实测错值也能拿 0.58，而这一条挡的是另一端——两条候选
        # 都不像图上的字时，比率再大也只是「两个都不像」里挑一个。
        return Judgement(
            decision=DECISION_HUMAN,
            winner=None,
            scores=scores,
            reason=REASON_PROB_LOW,
            ratio=ratio,
        )

    if ratio < ratio_min:
        # 规则 8：胜者与次高分拉不开距离。实测真值可以是 0.158、错值可以是 0.58（绝对值
        # 不可比），所以只认「相对差距」：差不到 ratio_min 倍就别自动采信。
        return Judgement(
            decision=DECISION_HUMAN,
            winner=None,
            scores=scores,
            reason=REASON_RATIO_LOW,
            ratio=ratio,
        )

    # 规则 9：胜者分够高 + 与次高分拉开足够距离 → 采信。
    return Judgement(
        decision=DECISION_ACCEPT,
        winner=best.text,
        scores=scores,
        reason=REASON_RATIO_OK,
        ratio=ratio,
    )


def _prob_of(score: CandidateScore) -> float:
    """排序/比较用的分数（``verdict != scored`` 时 ``prob_yes`` 为 ``None``，按 0 处理）。"""
    return score.prob_yes or 0.0


def _distinct_candidates(candidates: Sequence[str]) -> tuple[str, ...]:
    """按输入顺序去重，并丢掉空白候选。

    空白候选没有任何可判内容：送给打分器既浪费全局只有 2 的并发额度，又可能被上游判成
    非 ``scored``，把整次判定拖进 ``call_failed``。
    """
    seen: dict[str, None] = {}
    for text in candidates:
        if not text.strip():
            continue
        seen.setdefault(text, None)
    return tuple(seen)


def _score_all(*, settings: _Settings, image_data_url: str, texts: tuple[str, ...]) -> tuple[_ScoreResult, ...]:
    """逐条候选打分（同一判定内串行：全局并发额度只有 2，串行不会放大 429）。"""
    results: list[_ScoreResult] = []
    for text in texts:
        result = _score_candidate(settings=settings, image_data_url=image_data_url, text=text)
        results.append(result)
        if result.score.verdict == VERDICT_POLICY_REJECTED:
            # 结论已定（规则 4 优先于规则 5）：剩下的候选同样会被策略拒绝，不再耗请求。
            # 反过来，``failed`` **不**短路——若后面的候选是策略拒绝，规则 4 应当胜出。
            break
    return tuple(results)


def _score_candidate(*, settings: _Settings, image_data_url: str, text: str) -> _ScoreResult:
    """给一条候选打分：最多 ``_MAX_ATTEMPTS`` 次尝试，退避 0.5s / 1s / 2s（带抖动、总预算封顶）。

    失败一律转成 :class:`CandidateScore` 而不是抛：本模块的契约是 fail-open。
    """
    payload = _build_payload(image_data_url=image_data_url, text=text, model=JUDGE_MODEL)
    slept_seconds = 0.0
    detail = "retries_exhausted"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        outcome = _attempt_score(settings=settings, payload=payload, text=text)
        if outcome.result is not None:
            return outcome.result
        detail = outcome.detail
        if attempt >= _MAX_ATTEMPTS:
            break
        slept_seconds = _sleep_before_retry(attempt=attempt, slept_seconds=slept_seconds)
    return _ScoreResult(score=CandidateScore(text=text, prob_yes=None, verdict=VERDICT_FAILED, detail=detail))


def _attempt_score(*, settings: _Settings, payload: dict[str, Any], text: str) -> _Attempt:
    """发一次请求并分类结果：终局就返回结论，可重试就只返回原因。"""
    try:
        response = _post(settings=settings, payload=payload)
    except (httpx.HTTPError, OSError) as exc:
        # 网络异常/超时属可重试：实测本机代理隧道偶发提前断流，重试一轮通常就过。
        return _Attempt(result=None, detail=f"transport:{type(exc).__name__}")

    status = response.status_code
    if status == _RATE_LIMITED_STATUS or status >= _SERVER_ERROR_STATUS:
        return _Attempt(result=None, detail=f"http_{status}")
    if status in _AUTH_FAILED_STATUSES:
        # 401/403（key 缺失/无效/无权限）重试没有意义：同一条 key 不会自己变好。
        return _Attempt(result=_ScoreResult(score=_failed(text=text, detail=f"http_{status}")))
    if status == _BAD_REQUEST_STATUS and _POLICY_VIOLATION_CODE in response.text.lower():
        # 实测：真实证件图必被这条拒，且重试必然还拒 → 不可重试，直接判策略拒绝。
        return _Attempt(result=_ScoreResult(score=_rejected(text=text, detail=_POLICY_VIOLATION_CODE)))
    if status >= 400:
        return _Attempt(result=_ScoreResult(score=_failed(text=text, detail=f"http_{status}")))
    return _Attempt(result=_decode_score(response=response, text=text))


def _decode_score(*, response: httpx.Response, text: str) -> _ScoreResult:
    """解出打分结果与 token 用量；结构不符一律 ``failed``（响应体不进 detail，防带出原文）。"""
    try:
        payload = response.json()
    except ValueError:
        return _ScoreResult(score=_failed(text=text, detail="bad_json"))

    prompt_tokens, completion_tokens = _usage_tokens(payload)
    content = _message_content(payload)
    if content is None:
        return _ScoreResult(
            score=_failed(text=text, detail="no_content"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    return _ScoreResult(
        score=_decode_content(content=content, text=text),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _decode_content(*, content: str, text: str) -> CandidateScore:
    """把 ``choices[0].message.content`` 里的 JSON 字符串解成 :class:`CandidateScore`。

    ``verdict`` 可能不是 ``scored``（那时没有 ``prob_yes``）。契约里 verdict 只有三个取值，
    所以：上游明确给 ``policy_rejected`` 时保留该语义，其余非 ``scored`` 一律落 ``failed``
    （上游原词进 ``detail``）。
    """
    try:
        parsed = json.loads(content)
    except ValueError:
        return _failed(text=text, detail="bad_content_json")

    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return _failed(text=text, detail="no_results")

    item = results[0]
    verdict = str(item.get("verdict") or "").strip()
    if verdict == VERDICT_POLICY_REJECTED:
        return _rejected(text=text, detail=_POLICY_VIOLATION_CODE)
    if verdict != VERDICT_SCORED:
        return _failed(text=text, detail=f"verdict:{verdict[:32]}")

    prob_yes = _as_probability(item.get("prob_yes"))
    if prob_yes is None:
        return _failed(text=text, detail="prob_missing")
    return CandidateScore(
        text=text,
        prob_yes=prob_yes,
        verdict=VERDICT_SCORED,
        detail=str(item.get("detail") or "")[:_MAX_DETAIL_CHARS],
    )


def _failed(*, text: str, detail: str) -> CandidateScore:
    return CandidateScore(text=text, prob_yes=None, verdict=VERDICT_FAILED, detail=detail)


def _rejected(*, text: str, detail: str) -> CandidateScore:
    return CandidateScore(text=text, prob_yes=None, verdict=VERDICT_POLICY_REJECTED, detail=detail)


def _as_probability(raw: Any) -> float | None:
    """``prob_yes`` → ``[0, 1]`` 的浮点；非数字 / 越界 / NaN 一律 ``None``（→ ``failed``）。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        return None
    return value


def _usage_tokens(payload: Any) -> tuple[int, int]:
    """``(prompt_tokens, completion_tokens)``。

    实测 ``usage.completion_tokens`` 恒为 0（打分器不生成文本），所以真正有信息量的是
    ``prompt_tokens``；两个都记，便于事后算单次判定的成本。
    """
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return 0, 0
    return _as_token_count(usage.get("prompt_tokens")), _as_token_count(usage.get("completion_tokens"))


def _as_token_count(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return max(0, raw)


def _message_content(payload: Any) -> str | None:
    """``choices[0].message.content``——判别式打分器的结果是 **JSON 字符串**（实测口径）。"""
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return content


def _build_payload(*, image_data_url: str, text: str, model: str) -> dict[str, Any]:
    """实测请求体：图 + 候选文本两条 content，``minicpm_ocr_jev`` 走 ``mode="score"``。"""
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    # 候选文本必须原样送：打分器比的是「图上这段字」与「这个字符串」是否相符，
                    # 任何裁剪（去空格/截断）都会让比较的不是同一个东西。
                    {"type": "text", "text": text},
                ],
            }
        ],
        # 请求体的 category 与字段域同值（"text"）：复用同一个常量，免得两处各写一个 "text"
        # 之后悄悄漂移。
        "minicpm_ocr_jev": {"mode": _MODE_SCORE, "category": DOMAIN_TEXT},
        "stream": False,
    }


def _data_url(image_bytes: bytes) -> str:
    """PNG 字节 → ``data:image/png;base64,...``（实测口径；调用方需传 PNG）。"""
    return f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _headers(settings: _Settings) -> dict[str, str]:
    """``Authorization`` 只在配了 key 时带；没配时上游回 401，按「不可重试」处理。"""
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def _build_client(settings: _Settings) -> httpx.Client:
    """构造一次性客户端。``trust_env=False`` 是硬要求：实测本机代理环境变量会让上传/下载
    偶发失败、白重试一轮，判别式打分器必须直连。"""
    return httpx.Client(timeout=JUDGE_TIMEOUT_SECONDS, trust_env=False)


def _post(*, settings: _Settings, payload: dict[str, Any]) -> httpx.Response:
    """发一次请求（不重试、不限流以外不做别的事）；异常由调用方按可重试处理。"""
    with _GATE.slot(JUDGE_MAX_CONCURRENCY), _build_client(settings) as client:
        return client.post(JUDGE_API_URL, json=payload, headers=_headers(settings))


def _sleep_before_retry(*, attempt: int, slept_seconds: float) -> float:
    """第 ``attempt`` 次失败后的退避：0.5s → 1s → 2s（各加 ≤25% 抖动），总额封顶 3.5s。

    Returns:
        累计已睡秒数（总预算按它扣减，避免抖动把预算撑破）。
    """
    # 显式标 float：``random.uniform`` 的 stubs 返回 Any，不标会让下面整条算式退化成 Any
    # （mypy 的 warn_return_any 会直接报错）。
    base: float = min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_MAX_SECONDS)
    jitter: float = random.uniform(0.0, base * _BACKOFF_JITTER_RATIO)
    budget: float = max(0.0, _BACKOFF_TOTAL_CAP_SECONDS - slept_seconds)
    delay: float = min(base + jitter, budget)
    if delay <= 0.0:
        return slept_seconds
    time.sleep(delay)
    return slept_seconds + delay


def _load_settings() -> _Settings:
    """每次判定现读一遍配置（线上热改即时生效，单测可直接 monkeypatch）。

    只读两项：开关与 key。接口地址、模型名、并发上限、超时、两个阈值都是模块常量
    （见上方注释：工程常数不进配置表，避免被随手调坏且无声）。
    """
    return _Settings(
        enabled=_parse_bool(OCR_JUDGE_ENABLED_KEY, _config_value(OCR_JUDGE_ENABLED_KEY), default=False),
        api_key=_config_value(OCR_JUDGE_API_KEY_KEY),
    )


def _config_value(key: str) -> str:
    """读一个配置项（键不存在时用该键的默认值）；读不出来只 warning，绝不抛。"""
    default = _CONFIG_DEFAULTS[key]
    try:
        return str(SystemConfigService().get_value(key, default) or "").strip()
    except (ImportError, AttributeError, OSError, RuntimeError, TypeError, ValueError):
        logger.warning("ocr_judge_config_unreadable", extra={"key": key})
        return default


def _parse_bool(key: str, raw: str, *, default: bool) -> bool:
    value = raw.strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    _warn_invalid(key=key, raw=value, fallback=default)
    return default


def _warn_invalid(*, key: str, raw: str, fallback: object) -> None:
    """配置值不合法 → warning + 用默认值。``raw`` 只截前 32 字符（这一层只过布尔/数字型配置）。"""
    logger.warning("ocr_judge_config_invalid", extra={"key": key, "raw": raw[:32], "fallback": fallback})


def _mask(text: str) -> str:
    """把候选文本压成「前 8 字符 + 总长度」，**绝不输出完整原文**。

    卷宗文本里是姓名 / 证件号 / 金额，整段进日志等于把隐私写进文件与日志聚合平台。
    不超过 8 个字符时一个字符都不给（「张三」两字就是全文，打 8 个头字符等于打全文），
    只留长度；这也是「日志禁止出现完整候选文本」压过「前 8 字符」的地方。
    """
    if len(text) <= _MASK_HEAD_CHARS:
        return f"len={len(text)}"
    return f"{text[:_MASK_HEAD_CHARS]}…len={len(text)}"


def _record(
    judgement: Judgement,
    *,
    domain: str,
    started: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Judgement:
    """留痕：一条 info 日志 + 一份掩码快照（两者同源，避免日志与快照口径劈叉）。"""
    entry: dict[str, Any] = {
        "domain": domain,
        "decision": judgement.decision,
        "reason": judgement.reason,
        "ratio": None if judgement.ratio is None else round(judgement.ratio, 4),
        "latency_ms": int((time.monotonic() - started) * 1000),
        "tokens": completion_tokens,
        "prompt_tokens": prompt_tokens,
        "scores": [
            {"text": _mask(score.text), "verdict": score.verdict, "prob_yes": score.prob_yes}
            for score in judgement.scores
        ],
    }
    logger.info("ocr_disagreement_judge_done", extra=entry)
    with _SNAPSHOTS_LOCK:
        _SNAPSHOTS.append(entry)
    return judgement


def snapshot(limit: int = _SNAPSHOT_MAX) -> list[dict[str, Any]]:
    """最近 ``limit`` 次判定（时间正序，末尾是最新一次），供排障与人工抽屉展示。

    每条记录里的候选文本都已被 :func:`_mask` 压成「前 8 字符 + 长度」，没有原文。
    """
    if limit <= 0:
        return []
    with _SNAPSHOTS_LOCK:
        entries = list(_SNAPSHOTS)
    return entries[-limit:]
