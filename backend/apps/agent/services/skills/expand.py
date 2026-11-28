"""编排层 ``/skill:`` 展开：律师点名的一条技能 → 一段 ``<skill>`` 块。

## 为什么不能让后端自己展开

pi 1.6.0 的原生展开只认 ``text.startsWith("/skill:")``，而本仓**每一轮**都可能带前置
锚点行：``turn-send.ts`` 在案件/合同详情页拼 ``[当前业务：…]``、换页拼 ``[当前页面：…]``、
框选拼 ``[已引用选段：…]``，``stream.py`` 缺 pi session 时还会再拼一层
``render_transcript``。于是「详情页里敲 /skill:x」的原生命中率实际是 0（静默不展开），
而偶尔命中时又会把 ``<skill location="/Users/…/SKILL.md">`` 的宿主机绝对路径送进上下文。
展开统一收回到本模块：先剥锚点、再识别 ``/skill:``、正文从 DB 现取（用户技能不落盘）、
锚点原样拼回。

## 本模块的口径

1. 只在**开头连续**的锚点块被剥离，命中后原样拼回（模型仍要知道「这是哪个案件」）。
2. ``/skill:<name>`` 只在 ``body.lstrip()`` 处成立，且 name 后必须是空白或结尾。
3. name 只从 ``resolve_for_user`` 的可交付面里找——绝不按名直查 DB：已停用 / 草稿 /
   被遮蔽的名字一律原样透传，连「存在但没开」这种越权信息都不回显。
4. 纯 CPU：不写 DB、不发 HTTP、不落盘。``ExpandedPrompt.skill`` 只带
   ``{key, name, scope, version}``——它会落进 ``AgentMessage.metadata["expanded_skill"]``
   并被前端展示，**任何路径字段都不得出现在这里**。
"""

from __future__ import annotations

import importlib
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from . import constants, library, render

logger = logging.getLogger(__name__)

#: 前端注入的系统锚点块前缀（顺序即剥离顺序）。
#:
#: **必须覆盖全部五种**，不能只写 HANDOFF 举例的那三个：真正生成它们的地方是
#: ``store/turn-send.ts:53``（``[当前页面：``）、``domain/transcript.ts:23-25``
#: （``[已引用文件：`` / ``[已引用目录：``）、``domain/selection``（``[已引用选段：``）
#: 与详情页的 ``[当前业务：``。漏一个的后果是「在这个页面里 ``/skill:`` 不生效」——
#: 而它在别的页面又能用，看上去像随机故障。
ANCHOR_PREFIXES: tuple[str, ...] = (
    "[已引用选段：",
    "[已引用文件：",
    "[已引用目录：",
    "[当前业务：",
    "[当前页面：",
)

#: ``/skill:<name>``；name 的合法性交给 ``constants.NAME_RE``（与物化目录名同一口径）
_SKILL_COMMAND_RE = re.compile(r"/skill:(?P<name>\S+)")

#: 用户/共享技能总开关：``flags.py`` 由 CORE lane 提供，未合并时退回读这个环境变量
_USER_SKILLS_ENV = "FACHUAN_AGENT_USER_SKILLS"

_SCOPE_BUILTIN = "builtin"
_SCOPE_LAWYER = "lawyer"
_SCOPE_TEAM = "team"
_SCOPE_LAW_FIRM = "law_firm"
_VALID_SCOPES = frozenset({_SCOPE_BUILTIN, _SCOPE_LAWYER, _SCOPE_TEAM, _SCOPE_LAW_FIRM})

#: ``render.render_skill_body`` 未合并时的同构兜底（措辞与 CONTRACT §4 的 scope_preamble 一致）
_FALLBACK_PREAMBLE = {
    _SCOPE_BUILTIN: "> 随系统发布的内置指引。",
    _SCOPE_LAWYER: "> 本技能由律师本人编写，属个人工作习惯；与所内规范冲突时以所内规范为准。",
    _SCOPE_TEAM: "> 团队统一规范。",
    _SCOPE_LAW_FIRM: "> 全所统一规范，优先级高于个人技能；与个案判断冲突时请示审批人。",
}


@dataclass(frozen=True)
class ExpandedPrompt:
    """展开结果。``skill`` 非空时调用方应把它落进 ``metadata["expanded_skill"]``。"""

    prompt: str
    skill: dict[str, Any] | None  # {"key", "name", "scope", "version"}；未命中为 None


def expand_skill_prompt(*, user_id: int | None, text: str) -> ExpandedPrompt:
    """把用户消息里的 ``/skill:<name>`` 展开成 ``<skill>`` 块；未命中原样返回。

    ``user_id is None``（后台任务 / 单测）只认内置技能：没有用户就没有偏好与个人技能，
    凭空按名直查全库会绕开 ``resolve_for_user`` 的级联去重与权限口径。
    """
    anchors, body = _split_anchor_blocks(text)
    command = _match_command(body)
    if command is None:
        return ExpandedPrompt(prompt=text, skill=None)
    name, args = command
    entry = _find_entry(_candidates(user_id), name)
    if entry is None:
        return ExpandedPrompt(prompt=text, skill=None)
    body_text = _skill_body(entry)
    body_bytes = len(body_text.encode("utf-8"))
    if body_bytes > constants.MAX_BODY_BYTES:
        # 超限技能展开会把整轮上下文挤爆（pi 加载开销与正文长度挂钩），透传原文交模型处理
        logger.warning(
            "技能正文超过 %s 字节，本轮不展开 name=%s bytes=%s",
            constants.MAX_BODY_BYTES,
            name,
            body_bytes,
        )
        return ExpandedPrompt(prompt=text, skill=None)
    scope = _scope_of(entry)
    title = str(entry.get("title") or name)
    rendered = _render_body(scope=scope, name=name, title=title, body=body_text)
    block = f'<skill name="{name}" scope="{scope}">\n{rendered}\n</skill>\n{args}'
    logger.info("agent.skill_invoked name=%s scope=%s key=%s", name, scope, entry.get("key") or "")
    return ExpandedPrompt(prompt="\n".join([*anchors, block]), skill=_skill_metadata(entry, name=name, scope=scope))


def _split_anchor_blocks(text: str) -> tuple[list[str], str]:
    """剥离开头连续的系统锚点块，返回 ``(锚点行, 剩余正文)``。

    锚点块可以跨多行（选段原文理论上含换行），块尾只认「这一行以 ``]`` 结尾」一条；
    遇到第一个既不在块内、也不是锚点起始的行就停——正文中间出现同样字样不动，否则
    用户自己的正文会被当锚点吃掉。
    """
    lines = text.split("\n")
    anchors: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if not in_block and not stripped.startswith(ANCHOR_PREFIXES):
            break
        anchors.append(line)
        in_block = not stripped.endswith("]")
    return anchors, "\n".join(lines[len(anchors) :])


def _match_command(body: str) -> tuple[str, str] | None:
    """识别 ``body`` 开头的 ``/skill:<name>``，返回 ``(name, 剩余参数)``。

    name 必须是 ``constants.NAME_RE`` 的 slug：名字里混进标点（``/skill:foo，``）说明
    用户不是在点名技能，原样透传比猜一个近似名字安全——猜错就是拿别人的规范回话。
    参数只剥首尾空白：空白是命令行分隔符、不属参数内容；中间换行与缩进原样保留。
    """
    stripped = body.lstrip()
    match = _SKILL_COMMAND_RE.match(stripped)
    if match is None:
        return None
    name = match.group("name")
    if constants.NAME_RE.fullmatch(name) is None:
        return None
    return name, stripped[match.end() :].strip()


def _candidates(user_id: int | None) -> list[dict[str, Any]]:
    """点名候选集：有用户走唯一解析入口；无用户、或总开关关闭时只认内置。"""
    if user_id is None:
        return _builtin_candidates()
    from .resolve import resolve_for_user

    entries = list(resolve_for_user(user_id))
    if not _user_skills_enabled():
        # 回滚开关：DB 数据保留，但本轮只认随代码发布的内置技能（CONTRACT §12 #5）
        entries = [entry for entry in entries if _scope_of(entry) == _SCOPE_BUILTIN]
    return entries


def _builtin_candidates() -> list[dict[str, Any]]:
    """内置技能候选（附正文）。``library`` 只给清单字段，正文得现读随代码发布的那份。"""
    return [
        {**skill, "scope": _SCOPE_BUILTIN, "body": library.read_body(str(skill["name"]))}
        for skill in library.builtin_skills()
    ]


def _find_entry(entries: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """按 name 取第一条——解析入口已按 name 级联去重，同名只剩赢家。"""
    for entry in entries:
        if str(entry.get("name") or "") == name:
            return entry
    return None


def _skill_body(entry: dict[str, Any]) -> str:
    """条目正文。解析入口没带 ``body`` 时（内置条目）现读随代码发布的 SKILL.md。"""
    body = entry.get("body")
    if isinstance(body, str) and body.strip():
        return body
    if _scope_of(entry) == _SCOPE_BUILTIN:
        return library.read_body(str(entry.get("name") or ""))
    return str(body or "")


def _scope_of(entry: dict[str, Any]) -> str:
    """条目的作用域标签。

    未知 / 空值按个人处理：四档前言里个人那档说的是「个人习惯，冲突时以所内规范为准」，
    最保守，绝不会把来历不明的内容说成「全所统一规范」。
    """
    scope = str(entry.get("scope") or "")
    if scope in _VALID_SCOPES:
        return scope
    return _SCOPE_BUILTIN if entry.get("source") == "builtin" else _SCOPE_LAWYER


def _render_body(*, scope: str, name: str, title: str, body: str) -> str:
    """调 ``render.render_skill_body``；该函数由 CORE lane 新增，未合并时用同构兜底。

    两条路径都**不带 frontmatter**：块直接进模型上下文，``name`` / ``description``
    之类的 YAML 头只会是噪声，还会给「正文里伪造 frontmatter」留口子。
    """
    render_body = getattr(render, "render_skill_body", None)
    if callable(render_body):
        return str(render_body(scope=scope, name=name, title=title, body=body))
    preamble = _FALLBACK_PREAMBLE.get(scope, _FALLBACK_PREAMBLE[_SCOPE_LAWYER])
    return f"{preamble}\n\n{body.strip()}\n"


def _skill_metadata(entry: dict[str, Any], *, name: str, scope: str) -> dict[str, Any]:
    """落 ``metadata["expanded_skill"]`` 的最小留痕：只有这四个键，不含正文与路径。"""
    version = entry.get("version")
    return {
        "key": str(entry.get("key") or ""),
        "name": name,
        "scope": scope,
        "version": version if isinstance(version, int) else 0,
    }


def _user_skills_enabled() -> bool:
    """用户/共享技能总开关（``FACHUAN_AGENT_USER_SKILLS``）。

    优先走 ``flags.user_skills_enabled()``——子域开关只能有一个读法；该模块由 CORE
    lane 提供，尚未合并时按同一口径读环境变量（缺省 on，只有显式 ``off`` 才算关；
    ``dry`` 对「点名展开」等价于 on，只有提示块才区分）。
    """
    flag = _flag_function("user_skills_enabled")
    if flag is not None:
        return bool(flag())
    return os.environ.get(_USER_SKILLS_ENV, "").strip().lower() != "off"


def _flag_function(name: str) -> Callable[[], bool] | None:
    """取 ``services/skills/flags.py`` 里的开关函数；模块还没合并时返回 ``None``。

    用 ``importlib`` 而不是 ``from . import flags``：后者在模块缺失时是 ImportError、
    在 mypy 眼里却是「``skills`` 包没有这个属性」，且 CORE lane 补上 ``flags.py`` 之后
    那句 ``# type: ignore`` 又会变成 unused ignore。
    """
    try:
        module = importlib.import_module(f"{__package__}.flags")
    except ImportError:
        return None
    found = getattr(module, name, None)
    return cast("Callable[[], bool]", found) if callable(found) else None
