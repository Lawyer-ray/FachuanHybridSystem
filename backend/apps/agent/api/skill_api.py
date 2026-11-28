"""Agent 技能 API —— 管理抽屉（清单/详情/CRUD）+ 双轨发布生命周期 + 运行时正文出口。

端点前缀：``/api/v1/agent``（技能子域）。律师用 ``/skill:名字 参数`` 点名技能，
模型也可以经 MCP ``get_agent_skill`` 按需取全文——后者打的就是
``GET /skills/resolve/{name}/content``。

## 三条实现纪律

1. **路由顺序**：``/skills``、``/skills/quota``、``/skills/validate``、
   ``/skills/resolve/{name}/content`` 必须注册在 ``/skills/{key}`` **之前**。ninja 的
   URL 按声明顺序匹配，``{key}`` 的 ``[^/]+`` 会把后面的字面量段吞成参数值
   （症状是路由「永远 404」或「恒 405」，且没有任何报错）。
2. **API 层零 ORM**（四层棘轮）：查询、校验、权限、事务全在 ``services/skills/``；
   这里只做参数装配与「领域异常 → HTTP 状态码」的翻译。
3. **错误码有语义分工**：404 不存在/无权（不区分，避免探测）/ 403 越权 /
   409 冲突 / 422 字段级 / 429 配额 / **503 运营开关关闭**。唯一例外是运行时正文
   出口（``/skills/resolve/{name}/content``）：它只对「本人可见的」条目细分
   「未发布 / 已停用」，跨用户仍只有一句「技能不存在」（见 ``_unavailable_reason``）。

## 为什么 503 不能靠 ``SkillForbidden`` 翻出来

``services/skills/flags.py`` 关闭时服务层抛 ``SkillForbidden``，那会被翻译成 403。
但 403 的语义是「你没有这个权限」，前端据此会把律师引去申请权限——而这时候真正
该做的是找管理员打开开关。所以写端点在调服务层**之前**先看一眼开关（``_require_writes``）。
给 ``errors`` 新增 ``SkillDisabled`` 更干净，但 ``errors.py`` 不在本 lane 的边界内。

## 为什么 ``PATCH`` 单独留一条 ``ValueError`` 转换

``skill_service.set_skill_enabled`` 沿用了改造前「非法/未知内置名 → ``ValueError``」的
公开行为（它的调用方不止 API）。这条转换**只**留在启停端点：通用 ``_invoke`` 里宽捕
``ValueError`` 会把服务层任何笔误（例如 ``int("x")``）都翻译成 404，把真 bug 藏成
「技能不存在」。
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router, Status
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import (
    SkillContentOut,
    SkillCreateIn,
    SkillDetailOut,
    SkillDiffOut,
    SkillFieldError,
    SkillListOut,
    SkillOut,
    SkillQuotaOut,
    SkillReviewIn,
    SkillSafetyFinding,
    SkillSubmitIn,
    SkillToggleIn,
    SkillToggleOut,
    SkillTrialIn,
    SkillTrialOut,
    SkillUpdateIn,
    SkillValidateIn,
    SkillValidateOut,
)
from ..services import skill_service
from ..services.skills import errors as skill_errors
from ..services.skills import trial as skill_trial
from ..services.skills import flags, user_skills
from ..services.skills import review as skill_review
from ..services.skills.constants import CONTENT_PAGE_BYTES, USER_PREFIX
from ._helpers import _user_id

router = Router(tags=["Agent 技能"], auth=JWTOrSessionAuth())

#: ``GET /skills?scope=`` 的合法取值。``all`` 是缺省（返回全部可见条目）。
_SCOPE_FILTERS = frozenset({"all", "lawyer", "team", "law_firm", "builtin"})

#: ``POST /skills/{key}/review`` 的合法决策
_REVIEW_DECISIONS = frozenset({"approve", "reject"})


@contextlib.asynccontextmanager
async def _translating() -> AsyncIterator[None]:
    """把领域错误翻译成 ``HttpError``（一处实现，两条调用路径共用）。

    单独抽成上下文管理器，是因为下面的同步 service 与异步 service 必须共用**同一份**
    状态码映射：两处各写一遍，迟早会出现「同步端点 409、异步端点 500」这种
    只在那一个按钮上复现的分叉。
    """
    try:
        yield
    except skill_errors.SkillNotFound as exc:
        raise HttpError(404, str(exc)) from exc
    except skill_errors.SkillForbidden as exc:
        raise HttpError(403, str(exc)) from exc
    except skill_errors.SkillConflict as exc:
        raise HttpError(409, str(exc)) from exc
    except skill_errors.SkillQuotaExceeded as exc:
        raise HttpError(429, str(exc)) from exc
    except skill_errors.SkillInvalid as exc:
        raise HttpError(422, skill_errors.as_message(exc.errors)) from exc


async def _invoke(func: Any, **kwargs: Any) -> Any:
    """在线程里跑**同步** service，并把领域错误翻译成 ``HttpError``。

    ``thread_sensitive=True``：这些调用会进 ``transaction.atomic()``，必须回到主线程
    的单连接上跑，否则同一请求里的行锁与快照在两个连接上各说各话。
    """
    async with _translating():
        return await sync_to_async(func, thread_sensitive=True)(**kwargs)


async def _await_service(func: Any, **kwargs: Any) -> Any:
    """直接 ``await`` 一个**异步** service。

    单独一条路径而不是复用 ``_invoke``：``sync_to_async`` 只接受同步函数，塞进一个
    ``async def`` 会在**调用时**抛
    ``TypeError: sync_to_async can only be applied to sync functions``——那不是
    领域错误，上面的翻译接不住，最终表现为整条端点 500。试跑就是第一个异步 service。
    """
    async with _translating():
        return await func(**kwargs)


def _require_writes() -> None:
    """写端点前置拦截：运营开关 ``off`` 时 503（见模块 docstring 第 3 条）。"""
    if not flags.writes_enabled():
        raise HttpError(503, "技能写入已被运营开关关闭，请联系管理员")


async def _invoke_write(func: Any, **kwargs: Any) -> Any:
    """写端点的统一入口：先过总开关，再走 ``_invoke``。"""
    _require_writes()
    return await _invoke(func, **kwargs)


async def _await_write(func: Any, **kwargs: Any) -> Any:
    """写端点里的**异步** service：总开关 + 直接 await（见 ``_await_service``）。"""
    _require_writes()
    return await _await_service(func, **kwargs)


async def _invoke_toggle(func: Any, **kwargs: Any) -> Any:
    """启停专用：写开关 + ``ValueError → 404`` 兼容（见模块 docstring 末段）。"""
    _require_writes()
    try:
        return await _invoke(func, **kwargs)
    except ValueError as exc:
        raise HttpError(404, str(exc)) from exc


# ── 静态段路由（必须排在 /skills/{key} 之前）────────────────────


@router.get("/skills", response=SkillListOut)
async def list_skills(request: Any, scope: str = "all") -> SkillListOut:
    """管理抽屉清单：该律师可见的**全部**条目（含被遮蔽、草稿、待审）。

    ``scope`` 过滤在 API 侧做：``list_visible_skills`` 一次算出全部可见条目（含
    ``effective`` / ``shadowed_by`` / ``can_*``），按层过滤只是对同一份结果切片——
    放到服务层意味着每个 tab 都要重跑一遍级联。
    """
    wanted = (scope or "all").strip()
    if wanted not in _SCOPE_FILTERS:
        raise HttpError(422, f"scope 只能是 {' / '.join(sorted(_SCOPE_FILTERS))}")
    skills = await _invoke(user_skills.list_for_user, user_id=_user_id(request) or 0)
    if wanted != "all":
        skills = [item for item in skills if item["scope"] == wanted]
    return SkillListOut(skills=[SkillOut(**item) for item in skills])


@router.get("/skills/quota", response=SkillQuotaOut)
async def skill_quota(request: Any) -> SkillQuotaOut:
    """配额占用：个人与共享分开计数（前端进度条与「本所还剩几条」提示）。"""
    quota = await _invoke(user_skills.quota_for_user, user_id=_user_id(request) or 0)
    return SkillQuotaOut(**quota)


@router.post("/skills/validate", response=SkillValidateOut)
async def validate_skill(request: Any, payload: SkillValidateIn) -> SkillValidateOut:
    """字段级校验 + 渲染预览 + 安全命中（不落库，不写盘，不占开关）。"""
    result = await _invoke(
        user_skills.validate_form,
        user_id=_user_id(request) or 0,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        body=payload.body,
    )
    return SkillValidateOut(
        ok=bool(result["ok"]),
        errors=[SkillFieldError(**error) for error in result["errors"]],
        preview=str(result["preview"]),
        safety=[SkillSafetyFinding(**finding) for finding in result["safety"]],
    )


#: ``/content`` 取不到时给模型的固定三句原因（三种情形**对外只对本人细分**）。
#: 细分只在「这条技能对当前律师可见」时生效：别人的行不在可见集合里，跨用户一律
#: 「技能不存在」——否则这条出口就成了「存在但你无权看」的枚举口（与
#: ``user_skills.content_for_ref`` 的 404 红线是同一条）。
_UNAVAILABLE_NOT_PUBLISHED = "未发布：这条技能还在审批中，尚不可交付"
_UNAVAILABLE_DISABLED = "已停用：律师本人已停用这条技能"
_UNAVAILABLE_MISSING = "技能不存在"


def _ref_matches(entry: dict, ref: str) -> bool:
    """条目的 key / name 是否就是 ``ref``（口径同 ``user_skills._find_deliverable``）。"""
    raw = (ref or "").strip()
    if not raw:
        return False
    return entry.get("key") == raw or entry.get("name") == raw or entry.get("key") == f"{USER_PREFIX}{raw}"


def _unavailable_reason(user_id: int, ref: str) -> str:
    """``content_for_ref`` 说「取不到」之后，问一次「为什么」。

    数据源是管理抽屉的可见集合（``list_for_user`` 内部已过 ``permissions.can_view``）：
    只有 ``ref`` 真的对这位律师可见时才细分「未发布 / 已停用」；别人的技能根本不在
    这个集合里，因此跨用户仍然只有一句「技能不存在」。
    """
    hits = [entry for entry in user_skills.list_for_user(user_id) if _ref_matches(entry, ref)]
    # 停用优先于未发布：一条被本人关掉的共享技能，既是「没在交付」也是「他关的」，
    # 而模型该做的是同一个动作（不要重读）——先说清「是他关的」，他一看就懂。
    if any(entry.get("enabled") is False for entry in hits):
        return _UNAVAILABLE_DISABLED
    for entry in hits:
        if str(entry.get("status") or "") == "archived":
            # 已下线不是「审批中」：它已经不再交付，对外按不存在说
            continue
        # ``effective=False`` 且没有被同名条目遮蔽 = 这条本身不可交付（草稿 / 待审 /
        # 共享技能还没有已批准版本）。被遮蔽的那条按名字仍读得到，这里不算「未发布」。
        if entry.get("effective") is False and not entry.get("shadowed_by"):
            return _UNAVAILABLE_NOT_PUBLISHED
    return _UNAVAILABLE_MISSING


def _content_with_reason(user_id: int, ref: str, *, start: int, limit: int) -> dict:
    """``content_for_ref`` + 404 时把「为什么取不到」换成可区分的那一句。

    为什么补在 API 层：``user_skills.content_for_ref`` 不在本 lane 的边界内，而它那句
    合并口径的 404（「不存在 / 未发布 / 已停用」一句话）对管理面是正确的，对 MCP 的
    ``get_agent_skill`` 却不够——模型正在试跑一条还没发布的技能时，正文是内联注入的，
    它按名字回来重读会拿到「技能不存在」，于是要么以为工具坏了，要么换名字重试三轮。
    """
    try:
        return user_skills.content_for_ref(user_id, ref, start=start, limit=limit)
    except skill_errors.SkillNotFound as exc:
        raise skill_errors.SkillNotFound(_unavailable_reason(user_id, ref)) from exc


@router.get("/skills/resolve/{name}/content", response=SkillContentOut)
async def skill_content(
    request: Any,
    name: str,
    start: int = 0,
    limit: int = CONTENT_PAGE_BYTES,
) -> SkillContentOut:
    """**运行时**正文（MCP ``get_agent_skill`` 的数据源），按字节分段。

    ``name`` 这个路径段同时接受 ``builtin:<name>`` / ``skill:<uuid>`` / 裸 ``name``：
    模型只知道名字，而调用方手里常是 key。叫 ``name`` 而不是 ``ref`` 是有意的——
    MCP 工具面对模型暴露的参数就叫 ``name``，两边**同名**才能让「工具签名是否暴露了
    后端必填参数」这道跨语言契约门禁自动对齐（``test_output_contract``）；换个名字
    会让门禁只能靠注释说服人，而它本该靠签名说服人。

    严格走 ``resolve_for_user``——已停用 / 草稿 / 无权一律 404，这条出口给的是模型，
    不能像管理面那样把工作区草稿返出去。404 的消息按「这位律师自己可见的」三种情形
    细分（``未发布`` / ``已停用`` / ``技能不存在``，见 ``_unavailable_reason``）：模型
    凭这一句就能决定「用上下文里已注入的全文」还是「先看可用清单」，不必瞎猜是工具坏了。
    """
    content = await _invoke(
        _content_with_reason,
        user_id=_user_id(request) or 0,
        ref=name,
        start=start,
        limit=limit,
    )
    return SkillContentOut(**content)


# ── 单条路由（``{key}`` 只能出现在静态段之后）────────────────────


@router.get("/skills/{key}", response=SkillDetailOut)
async def get_skill(request: Any, key: str) -> SkillDetailOut:
    """技能详情（管理面）：**工作区**最新正文，作者要能接着编辑自己的稿子。

    ``key`` 可含 ``:``（``builtin:web-research``）。运行时正文走
    ``/skills/resolve/{name}/content``，两者刻意分开：一个是工作区，一个是线上。
    """
    detail = await _invoke(user_skills.get_detail, user_id=_user_id(request) or 0, key=key)
    return SkillDetailOut(**detail)


@router.post("/skills", response={201: SkillDetailOut})
async def create_skill(request: Any, payload: SkillCreateIn) -> Any:
    """新建技能（缺省个人）；``scope=law_firm`` / ``team`` 的服务端权限闸门在 service。"""
    detail = await _invoke_write(
        user_skills.create_skill,
        user_id=_user_id(request) or 0,
        name=payload.name,
        title=payload.title,
        description=payload.description,
        body=payload.body,
        scope=(payload.scope or "lawyer").strip(),
        team_id=payload.team_id,
    )
    return Status(201, SkillDetailOut(**detail))


@router.put("/skills/{key}", response=SkillDetailOut)
async def update_skill(request: Any, key: str, payload: SkillUpdateIn) -> SkillDetailOut:
    """更新**工作区**（共享技能编辑不换线上：``version`` 不符 409）。"""
    detail = await _invoke_write(
        user_skills.update_skill,
        user_id=_user_id(request) or 0,
        key=key,
        title=payload.title,
        description=payload.description,
        body=payload.body,
        expected_version=payload.version,
    )
    return SkillDetailOut(**detail)


@router.patch("/skills/{key}", response=SkillToggleOut)
async def toggle_skill(request: Any, key: str, payload: SkillToggleIn) -> SkillToggleOut:
    """启停。共享技能只 upsert 本人偏好行（``AgentSkill.enabled`` 是全所共用的一行）。"""
    result = await _invoke_toggle(
        skill_service.set_skill_enabled,
        user_id=_user_id(request) or 0,
        key=key,
        enabled=payload.enabled,
    )
    return SkillToggleOut(key=str(result["key"]), enabled=bool(result["enabled"]))


@router.delete("/skills/{key}", response={204: None})
async def delete_skill(request: Any, key: str) -> Any:
    """删除个人技能（内置 403；别人的 404；共享只能由本所管理员删）。"""
    await _invoke_write(user_skills.delete_skill, user_id=_user_id(request) or 0, key=key)
    return Status(204, None)


@router.post("/skills/{key}/duplicate", response={201: SkillDetailOut})
async def duplicate_skill(request: Any, key: str) -> Any:
    """「复制为我的」：仅内置技能可复制（内置名是保留字，副本名加 ``-copy``）。"""
    detail = await _invoke_write(user_skills.duplicate_builtin, user_id=_user_id(request) or 0, key=key)
    return Status(201, SkillDetailOut(**detail))


@router.get("/skills/{key}/diff", response=SkillDiffOut)
async def diff_skill(request: Any, key: str, v1: int | None = None, v2: int | None = None) -> SkillDiffOut:
    """两版对比，缺省「线上生效版 vs 工作区」。

    只读接口（作者与审批人都要看）：所以不过写开关。
    """
    diff = await _invoke(skill_review.diff_versions, user_id=_user_id(request) or 0, key=key, v1=v1, v2=v2)
    return SkillDiffOut(**diff)


@router.post("/skills/{key}/submit", response=SkillDetailOut)
async def submit_skill(request: Any, key: str, payload: SkillSubmitIn) -> SkillDetailOut:
    """提审：置 ``review_status=pending``，**不动线上**（生效的唯一入口是 approve）。"""
    detail = await _invoke_write(
        skill_review.submit,
        user_id=_user_id(request) or 0,
        key=key,
        target_scope=(payload.target_scope or "").strip(),
        note=payload.note,
        acknowledged_firm_wide=payload.acknowledged_firm_wide,
        new_name=payload.name,
        team_id=payload.team_id,
    )
    return SkillDetailOut(**detail)


@router.post("/skills/{key}/trial", response=SkillTrialOut)
async def trial_skill(request: Any, key: str, payload: SkillTrialIn) -> SkillTrialOut:
    """发布前试跑：真跑一轮，把模型回复交给审批人（**不写会话历史、不可能写业务**）。

    这是个**慢端点**（起一个 pi 子进程 + 一轮模型调用，默认上限 90 秒）。前端必须
    给它独立的等待态，不能沿用列表操作那种「点完就回来」的交互。
    """
    result = await _await_write(
        skill_trial.run_trial,
        user_id=_user_id(request) or 0,
        key=key,
        question=payload.question,
        backend_kind=payload.backend,
    )
    return SkillTrialOut(
        ok=result.ok,
        text=result.text,
        backend=result.backend,
        model=result.model,
        duration_ms=result.duration_ms,
        skill_key=str(result.skill["key"]),
        skill_name=str(result.skill["name"]),
        skill_scope=str(result.skill["scope"]),
        skill_version=int(result.skill["version"]),
        injected=result.injected,
        tool_calls=list(result.tool_calls),
        error=result.error,
    )


@router.post("/skills/{key}/review", response=SkillDetailOut)
async def review_skill(request: Any, key: str, payload: SkillReviewIn) -> SkillDetailOut:
    """审批：``approve`` 把最新快照提为线上版；``reject`` 只改修订流（线上纹丝不动）。"""
    decision = (payload.decision or "").strip().lower()
    if decision not in _REVIEW_DECISIONS:
        raise HttpError(422, f"decision 只能是 {' / '.join(sorted(_REVIEW_DECISIONS))}")
    if decision == "approve":
        detail = await _invoke_write(
            skill_review.approve,
            user_id=_user_id(request) or 0,
            key=key,
            acknowledged_firm_wide=payload.acknowledged_firm_wide,
        )
    else:
        detail = await _invoke_write(
            skill_review.reject,
            user_id=_user_id(request) or 0,
            key=key,
            note=payload.note,
        )
    return SkillDetailOut(**detail)


@router.post("/skills/{key}/archive", response=SkillDetailOut)
async def archive_skill(request: Any, key: str) -> SkillDetailOut:
    """下线：立刻退出交付面，但保留 ``published_revision`` 供审计追溯。"""
    detail = await _invoke_write(skill_review.archive, user_id=_user_id(request) or 0, key=key)
    return SkillDetailOut(**detail)


@router.post("/skills/{key}/restore", response=SkillDetailOut)
async def restore_skill(request: Any, key: str) -> SkillDetailOut:
    """恢复：``archived → draft``，**必须重走审批**（恢复即生效等于绕过一次审批）。"""
    detail = await _invoke_write(skill_review.restore, user_id=_user_id(request) or 0, key=key)
    return SkillDetailOut(**detail)


@router.post("/skills/{key}/discard-draft", response=SkillDetailOut)
async def discard_draft(request: Any, key: str) -> SkillDetailOut:
    """放弃工作区：把线上已批准版回填到工作区，清掉待审/驳回态。"""
    detail = await _invoke_write(skill_review.discard_draft, user_id=_user_id(request) or 0, key=key)
    return SkillDetailOut(**detail)
