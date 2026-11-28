"""Agent 技能工具面 —— 内置 / 个人 / 所内技能（法穿）的读半边与写半边。

## 为什么读技能是一个工具而不是全塞进系统提示词

系统提示词（AGENTS.md）每轮全量注入：全部 440+ 工具的操作指引如果常驻，
上下文成本高且不聚焦。把场景化指引拆成技能包（SKILL.md，Agent Skills
规范格式），AGENTS.md 只保留一行路由，模型遇到对应场景时用本工具按名
取全文——「按需加载」。

pi 原生 Skills 机制要求模型用 read/bash 工具读技能文件，而本系统出于
安全不向模型声明任何文件读取工具（防提示注入直通服务器文件面），所以
技能内容经由 MCP 工具面供给。

## 两条来源，一条读路径

- **内置技能**：随代码发布的 4 个 ``apps/agent/pi/skills/*/SKILL.md``；
- **个人 / 团队 / 所内技能**：DB 直出（P1 起取消任何磁盘物化，见
  ``docs/analysis/user-skills-copilot-2026-11-28/CONTRACT.md`` §0 方案 A）。

有用户上下文（HTTP 模式透传 ``Authorization``）时一律走
``GET /agent/skills/resolve/{ref}/content``：**只有 ``resolve_for_user`` 知道
「这位律师停用了哪个技能」「所内技能线上生效的是哪一版」**。工具直接扫盘
会绕过停用偏好与共享审批版（读静态盘 = 绕过偏好），所以静态文件只在
无用户上下文的本地 stdio / 单测里兜底，且只认内置技能目录名。

## 安全

- 静态回落的名字白名单 = 技能目录下实际存在的子目录名（正则 + 实存双校验），
  路径穿越（``../``、斜杠、绝对路径）一律拒绝；
- 写工具只写**律师本人**作用域；删除 / 提审只认个人技能的 ``key``，
  共享层（团队 / 所内）的发布由律师在技能抽屉里走审批，模型无权代办。
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import FachuanApiError, client
from mcp_server.identity import passthrough_authorization

#: 技能包根目录：apps/agent/pi/skills（与 AGENTS.md 模板同处，随代码发布）
_DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[3] / "apps" / "agent" / "pi" / "skills"

#: 合法技能名：小写字母/数字/连字符（Agent Skills 规范），不含路径分隔符。
#: 与 ``apps/agent/services/skills/constants.py`` 的 ``NAME_RE`` 同构。
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: 技能 key 的两段前缀（与 ``services/skills/constants.py`` 同源）：
#: ``builtin:<name>`` 是随代码发布的目录，``skill:<uuid>`` 是数据库行。
_BUILTIN_PREFIX = "builtin:"
_USER_PREFIX = "skill:"
_USER_KEY_RE = re.compile(r"^skill:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")

#: 部署异位（如容器内路径不同）时的覆盖入口
_SKILLS_DIR_ENV = "FACHUAN_AGENT_SKILLS_DIR"

#: 单次返回正文的字节上限。宿主 pi 对工具输出按 20480 字节拦腰截断
#: （``server._TRUNCATION_WARN_BYTES`` 的实测口径）：信封与元数据约 1KB，
#: 正文留给 16000 字节，截断发生在截断线**之前**且可续读，模型收到的永远是
#: 完整字符（UTF-8 安全切分，不会把中文切坏）。与 REST 端点 ``?limit=16000``
#: 同口径。
_CONTENT_BYTE_BUDGET = 16_000

#: ``client`` 的 REST 错误固定以 ``HTTP <status>: <响应体>`` 开头（见 ``client._handle``）
_HTTP_STATUS_RE = re.compile(r"^HTTP (?P<status>\d{3}):\s*")

#: 后端 ``/content`` 的 404 原因前缀（与 ``apps/agent/api/skill_api.py`` 的固定三句同源）。
#: 只用来区分「业务性取不到」（这条技能存在但不可交付）与环境性 404（端点不在 /
#: 旧后端）——前者必须原样告诉模型，后者仍走原来的静态回落。
_UNAVAILABLE_REASON_PREFIXES = ("未发布：", "已停用：", "技能不存在")

#: 404 的可操作提示：正文可能已经内联在上下文里（试跑待审技能就是这么跑的）
_NOT_FOUND_HINT = (
    "取不到「{name}」：{reason}。\n"
    "如果你正在阅读一条尚未发布/刚被停用的技能，请直接使用已经注入到你上下文里的技能全文，\n"
    "不要反复按名字重读；如果你只是记错了名字，可以先调 list_my_skills 看可用清单。"
)


def _skills_root() -> Path:
    override = os.environ.get(_SKILLS_DIR_ENV, "").strip()
    return Path(override) if override else _DEFAULT_SKILLS_ROOT


def available_skill_names() -> list[str]:
    """当前技能包目录下全部可用内置技能名（按目录名排序，供错误提示与测试）。"""
    root = _skills_root()
    if not root.is_dir():
        return []
    return sorted(p.parent.name for p in root.glob("*/SKILL.md"))


def _builtin_name(name: str) -> str:
    """内置技能名归一 + 实存校验；不是内置技能就抛 ``ValueError``。"""
    lowered = (name or "").strip().lower()
    normalized = lowered[len(_BUILTIN_PREFIX) :] if lowered.startswith(_BUILTIN_PREFIX) else lowered
    if not _NAME_RE.fullmatch(normalized):
        raise ValueError(f"非法技能名: {name!r}（只能用 1-64 位小写字母、数字与连字符）")
    skill_file = _skills_root() / normalized / "SKILL.md"
    # 双校验：正则已挡住路径分隔符；resolve 后必须仍在技能根目录内（防 symlink 逃逸）
    if not skill_file.is_file() or skill_file.resolve().parent.parent != _skills_root().resolve():
        available = "、".join(available_skill_names()) or "（无）"
        raise ValueError(f"未知技能: {name!r}，可用技能: {available}")
    return normalized


def _normalize_ref(name: str) -> str:
    """把模型给的 ``name`` 收敛成 REST 认的 ``{ref}``（裸名 / ``builtin:`` / ``skill:``）。

    模型只知道命令名（``contract-review``），但 REST 同时接受 key；这里统一
    归一，并**挡住**任何带路径分隔符或其它前缀的脏输入——``{ref}`` 会被拼进
    URL 路径，不做白名单就是一条注入面。
    """
    lowered = (name or "").strip().lower()
    if lowered.startswith(_USER_PREFIX):
        if not _USER_KEY_RE.fullmatch(lowered):
            raise ValueError(f"非法技能 key: {name!r}（个人技能的 key 形如 skill:<uuid>，取自 list_my_skills）")
        return lowered
    is_builtin = lowered.startswith(_BUILTIN_PREFIX)
    normalized = lowered[len(_BUILTIN_PREFIX) :] if is_builtin else lowered
    if not _NAME_RE.fullmatch(normalized):
        raise ValueError(f"非法技能名: {name!r}（只能用 1-64 位小写字母、数字与连字符）")
    return f"{_BUILTIN_PREFIX}{normalized}" if is_builtin else normalized


def _byte_window(text: str, start: int) -> dict[str, Any]:
    """取正文的一个字节窗口（UTF-8 安全：不把多字节字符切两半）。"""
    raw = text.encode("utf-8")
    total = len(raw)
    if start < 0 or start > total:
        raise ValueError(f"start={start} 越界：正文共 {total} 字节（从 0 起算）")
    content = raw[start : start + _CONTENT_BYTE_BUDGET].decode("utf-8", errors="ignore")
    # 续读偏移按**实际送达**的字节数推进：字节刀落在多字节字符中段时
    # errors="ignore" 会丢掉残字，用原始 start+limit 会把这几个字节跳过。
    next_start = start + len(content.encode("utf-8"))
    truncated = next_start < total
    return {
        "content": content,
        "start": start,
        "total_bytes": total,
        "truncated": truncated,
        "next_start": next_start if truncated else None,
    }


def _static_skill(name: str, start: int) -> dict[str, Any]:
    """内置技能的本地静态窗口（无用户上下文时唯一的来源）。

    只认技能目录下真实存在的子目录名：内置技能随代码发布、内容在盘上；而
    用户/所内技能只有数据库里有，盘上**没有**副本（方案 A 取消磁盘物化），
    所以对非内置名不做任何猜测。
    """
    normalized = _builtin_name(name)
    skill_file = _skills_root() / normalized / "SKILL.md"
    return {
        "key": f"{_BUILTIN_PREFIX}{normalized}",
        "name": normalized,
        "scope": "builtin",
        "version": 0,
        **_byte_window(skill_file.read_text(encoding="utf-8"), start),
    }


def _static_fallback(name: str, start: int, exc: FachuanApiError) -> dict[str, Any]:
    """REST 不可用时的回落：内置名读盘；非内置名把真实原因抛给模型。

    非内置名没有本地副本可回落——把 REST 的错误原因与「它不是内置技能」一起
    说清，模型才不会把「读不到」含糊成「这个技能不存在」，也不会凭记忆编造。
    """
    try:
        return _static_skill(name, start)
    except ValueError as static_exc:
        raise ValueError(
            f"读取技能 {name!r} 失败：{exc}。{static_exc}。"
            "非内置技能没有本地副本可回落，请告知律师稍后再试（不要凭记忆编造技能内容）。"
        ) from exc


def _backend_detail(message: str) -> str:
    """从 ``HTTP <status>: <响应体>`` 里取出后端那句话（``{"code", "message"}`` → 中文原文）。

    ``client`` 只保留了 ``str(响应体)``；后端 4xx 的体是 ``{"code": "HTTP_ERROR",
    "message": "…", "error": "…"}``（见 ``apps/core/exceptions/handlers.py``），原样
    塞给模型就是一坨字典字面量，看不出哪句是原因。
    """
    raw = _HTTP_STATUS_RE.sub("", message, count=1).strip()
    if not raw.startswith("{"):
        return raw
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        # 响应体不是 Python 字面量（例如已经被人手改过）：原样交给模型，不猜
        return raw
    if isinstance(parsed, dict):
        for field in ("message", "detail"):
            text = parsed.get(field)
            if isinstance(text, str) and text.strip():
                return text.strip()
    return raw


def _not_found_reason(exc: FachuanApiError) -> str | None:
    """后端 404 且说了「取不到的原因」时返回那句原因，其余一概 ``None``。

    ``None`` 是「保持原行为」的信号：5xx / 超时 / 网络故障 / 端点不在都不能被包装成
    「技能不存在」——真正的故障伪装成业务语义，模型就会去改名字重试而不是报告故障。
    """
    message = str(exc)
    match = _HTTP_STATUS_RE.match(message)
    if match is None or int(match.group("status")) != 404:
        return None
    detail = _backend_detail(message)
    return detail if detail.startswith(_UNAVAILABLE_REASON_PREFIXES) else None


def get_agent_skill(
    name: Annotated[
        str,
        Field(description="技能名（命令名 slug，如 contract-review）；也接受 key 形式 builtin:<name> / skill:<uuid>"),
    ],
    start: Annotated[
        int,
        Field(description="正文起始字节偏移（默认 0 从头读）；truncated=true 时传上一次返回的 next_start 续读", ge=0),
    ] = 0,
) -> dict[str, Any]:
    """读取一份技能指引的全文（内置技能 + 律师个人 / 所内技能）。

    遇到以下场景时，先调用本工具读取对应指引再决定用哪些工具、怎么传参：
    - 期限 / 排期 / 开庭 / 到期 / 异步任务进度 → ``deadline-queries``
    - 列表 / 汇总 / 统计 / 取明细 → ``list-projection``
    - 读材料 / 解析文档 / 提取正文表格 → ``materials-parsing``
    - 联网搜索 / 查法条 / 抓网页原文 → ``web-research``

    **用户 / 所内技能**：系统提示里会给你索引，列在 ``## 可用技能（法穿）`` 中
    （例如 ``- [所内] contract-review：《合同审查三段式》——审阅合同时使用…``）。
    遇到索引里描述的场景，先按索引给的名字调本工具读全文再动手：索引只有一行
    描述，别拿描述当全文用；也不要凭记忆编造没读过的技能内容。索引里没有、
    律师也没点名的技能，不要自行猜测名字。

    返回 ``name`` 与 ``content``（Markdown 正文，已渲染）。正文按 16000 字节
    分段：``truncated=true`` 时带 ``start=next_start`` 续读，直到
    ``truncated=false``——多步骤任务前必须读完整，只读半段就执行会漏掉后半段
    的约束。

    Args:
        name: 技能名（命令名 slug，如 ``deadline-queries``）。也接受 key 形式
            （``builtin:<name>`` / ``skill:<uuid>``，``list_my_skills`` 返回的
            就是 key），模型通常只需传名字。
        start: 起始字节偏移，默认 0（从头读）；续读时传上一次的 ``next_start``。

    **本工具只取「已经交付」的技能**：未发布（还在审批/试跑）/ 律师本人已停用 / 无权
    访问的技能一律取不到，这是设计而不是故障——待审技能的正文由系统**内联注入**，
    不在这条按名读取的路径上。碰到 404 时错误消息会说明是哪一种：直接用手上已有的
    全文继续，不要换个名字重试、也不要假设它的内容。
    """
    ref = _normalize_ref(name)
    if passthrough_authorization():
        try:
            result: dict[str, Any] = client.get(f"/agent/skills/resolve/{ref}/content", params={"start": start})
        except FachuanApiError as exc:
            reason = _not_found_reason(exc)
            if reason is not None:
                raise FachuanApiError(_NOT_FOUND_HINT.format(name=name, reason=reason)) from exc
            return _static_fallback(name, start, exc)
        return result
    return _static_skill(name, start)


def list_my_skills() -> dict[str, Any]:
    """列出当前律师**现在就能用**的技能（已生效、未停用）。

    什么时候用：
    - 律师问「我有哪些技能」「能不能按我的习惯来」；
    - 需要 ``key``（``skill:<uuid>``）去调 ``delete_user_skill`` /
      ``submit_skill_for_review``——那两个工具只认 key，不认名字。

    返回 ``{"skills": [{key, name, title, description, scope}]}``：``name`` 是
    律师用 ``/skill:名字`` 点名、也是 ``get_agent_skill`` 取全文用的命令名；
    ``scope`` 是 ``builtin`` / ``lawyer`` / ``team`` / ``law_firm``，决定它与
    所内规范冲突时以谁为准（所内 > 团队 > 个人 > 内置）。

    本工具只读、零副作用：不改任何状态，空列表就是律师真的没有可用技能。
    """
    data: dict[str, Any] = client.get("/agent/skills")
    entries = list((data or {}).get("skills") or [])
    return {
        "skills": [
            {
                "key": str(item.get("key") or ""),
                "name": str(item.get("name") or ""),
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or ""),
                "scope": str(item.get("scope") or ""),
            }
            for item in entries
            # ``GET /agent/skills`` 是管理抽屉面（含停用项与被遮蔽的低优先级条目），
            # 工具面只交付已生效集合——与 ``resolve_for_user`` 同口径。
            if item.get("enabled") is not False and item.get("effective") is not False
        ]
    }


def save_user_skill(
    name: Annotated[
        str,
        Field(description="命令名 slug（1-64 位小写字母、数字、连字符，如 my-style）；律师之后用 /skill:<name> 点名"),
    ],
    title: Annotated[str, Field(description="显示名（中文，≤64 字），出现在技能列表与 / 菜单")],
    description: Annotated[
        str, Field(description="单行路由描述（≤400 字）：写清什么场景该用它，决定模型以后何时想起这条技能")
    ],
    body: Annotated[str, Field(description="正文（Markdown，≤32KB）：具体的做法、步骤、格式要求与范例")],
) -> dict[str, Any]:
    """新建一条**个人**技能（只写律师本人的作用域，不进团队 / 所内）。

    什么时候用：律师明确要沉淀一条可复用的工作规范——「记下这个做法，以后都
    这么干」「把这个流程存成技能」。一次性任务、某个案件的结论、当事人姓名、
    案号、金额、日期都不要写成技能（那些走业务工具或记忆工具）。

    会持久化什么：``title`` / ``description`` / ``body`` 三段全部落库并成为
    **此后每轮对话都会带给模型的指令**（``description`` 进系统提示的技能索引，
    ``body`` 在模型按需读全文时给出）。因此提交后律师会在审批卡上看到全文，
    他签字之后才真正保存——不要把律师没说过的话写进去，也不要自己发挥补充
    他没要求的规则。

    约束：
    - ``name`` 必须显式给：同名会 409 冲突，绝不静默覆盖已有技能（也不会
      因为重试而建出两条）；
    - 内置技能名是保留字，不能占用；个人技能配额 20 条、正文上限 32KB；
    - 想改已有技能请让律师在技能抽屉里编辑（本工具只负责新建）。

    返回新建技能的 ``key`` / ``name`` / ``title`` / ``description`` / ``scope`` /
    ``version``（**不回显正文**：正文最大 32KB，原样回显会撞上 pi 的 20KB 输出
    截断线变成坏 JSON，而模型不需要把自己刚写过的正文再读一遍）。
    """
    payload = {"name": name, "title": title, "description": description, "body": body}
    result: dict[str, Any] = client.post("/agent/skills", json=payload)
    return {
        "key": str(result.get("key") or ""),
        "name": str(result.get("name") or ""),
        "title": str(result.get("title") or ""),
        "description": str(result.get("description") or ""),
        "scope": str(result.get("scope") or ""),
        "version": int(result.get("version") or 0),
        "note": "已保存（个人作用域）；正文需要时用 get_agent_skill 按名重新读取。",
    }


def delete_user_skill(
    key: Annotated[str, Field(description="技能 key，形如 skill:<uuid>，取自 list_my_skills；名字不是 key")],
) -> dict[str, Any]:
    """删除一条**个人**技能（不可撤销；内置技能删不了，只能停用）。

    什么时候用：律师明确说「这个技能不要了 / 删掉它」。只是暂时不用请让他在
    技能抽屉里停用——停用可随时开回来，删除把历史和修订链一起抹掉。

    会持久化什么：直接删掉 ``key`` 对应的技能行及其修订链，此后这一轮与所有
    后续会话都不再看到它；删除前请把技能名念给律师确认一次。团队 / 所内技能
    不在本工具权限内（模型只能删律师自己写的），共享层的下线由律师在抽屉里走
    审批。

    Args:
        key: 技能 key，形如 ``skill:<uuid>``，取自 ``list_my_skills``。传名字会
            404——名字不是 key。

    返回 ``key`` 与 ``deleted=true``。
    """
    ref = _normalize_ref(key)
    client.delete(f"/agent/skills/{ref}")
    return {"key": ref, "deleted": True}


def submit_skill_for_review(
    key: Annotated[str, Field(description="技能 key，形如 skill:<uuid>，取自 list_my_skills")],
    target_scope: Annotated[
        Literal["law_firm", "team"],
        Field(description="提审目标层：law_firm（全所）或 team（团队）"),
    ],
    note: Annotated[str, Field(description="给审批人的一句话说明（为什么值得推广到团队 / 全所），可空")] = "",
) -> dict[str, Any]:
    """把一条个人技能提审到团队 / 所内（只是提交申请，不是发布）。

    什么时候用：律师说「把这个做法推广给团队 / 全所」。他只想自己用就别提审
    ——提审会在管理员那儿挂一条待办。

    会持久化什么：技能行上记 ``review_status=pending``、提审说明与目标层，
    管理员在技能抽屉里批准后才生效（批准前运行时读到的仍是原来的正文）。
    提审**不改变**线上生效的任何内容；被驳回会带理由回到律师手里。

    Args:
        key: 技能 key，形如 ``skill:<uuid>``，取自 ``list_my_skills``。
        target_scope: 提审目标层：``law_firm``（全所）或 ``team``（团队）。
        note: 给审批人的说明（为什么值得推广），可空。

    返回提审结果：技能进入待审（``review_status=pending``）。驳回会在
    ``review_note`` 里带理由。
    """
    ref = _normalize_ref(key)
    payload = {"target_scope": target_scope, "note": note}
    result: dict[str, Any] = client.post(f"/agent/skills/{ref}/submit", json=payload)
    return result
