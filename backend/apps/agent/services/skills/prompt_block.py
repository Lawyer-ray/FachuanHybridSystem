"""技能索引块：把「这一轮律师能用哪些技能」压进系统提示的一小段固定文本。

## 为什么块首必须是 ``## 可用技能（法穿）``

pi 把 ``--append-system-prompt`` 的值既当提示文本、又当「可能是个文件路径」：
``resource-loader.js`` 对以路径形态出现的参数会走 ``existsSync`` 分支去读文件。
块首是 markdown 标题而不是 ``/`` 开头的绝对路径，这条分支永远不会命中，
即使某个技能标题被写成路径形态也一样。

## 两轮裁剪，禁止同循环 ``break`` 吞尾

预算用满时剩余条目**不是**整块丢掉，而是降级成「只留名字」的第二轮；仍然放不下的
才进 ``not_injected`` 交给调用方回传前端提示。一个 ``for`` 里 ``break`` 会把
「所内规范太多」静默变成「后面的个人技能全部消失」，正是 ``memory/snapshot.py``
已经踩过的坑。

第一轮升「完整行」前会先给**后面每一条**预留它那行名字的位置：不留这个余量，前几条
长描述就能把后面的技能整体挤成 ``not_injected``——而索引块的用处正是让模型知道
「还有哪些技能可用」，名字都看不见等于没发布。

## 顺序即优先级，本模块**不排序**

入参已是 ``resolve_for_user`` 按 ``(scope_weight, name)`` 排好的顺序：高优先级的
所内 / 团队条目先占完整行，个人技能排后面。这里再排一次只会让两处口径打架；按
``updated_at`` 之类动态字段排序则会每轮打乱块前缀，prompt cache 前缀失效。
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Callable, Sequence
from typing import Any, cast

#: 索引块总预算（字，≈1.5k token）：整块（含标题与说明行）不超过这个长度
SKILL_INDEX_BUDGET = 4000
#: 单条描述截断长度（超出加 ``…``）
PER_ITEM_DESCRIPTION_MAX = 220
#: 块首标题：**同时是「这不是文件路径」的形状保险**，不要改前缀
BLOCK_HEADING = "## 可用技能（法穿）"

#: 块首第二行：告诉模型「怎么取全文」，缺了它索引块只是个技能名清单
_INSTRUCTION = "以下场景如有对应专项规范，动手前先调 `get_agent_skill(名称)` 读取全文："

#: 块首两行（裁剪时按「行文本 + 1 个换行」计入预算）
_HEADER: tuple[str, str] = (BLOCK_HEADING, _INSTRUCTION)

#: scope → 中文标签；未知 scope 按个人处理（见 ``_scope_of``），不谎称是所内规范
_SCOPE_LABELS = {"builtin": "内置", "lawyer": "我的", "team": "团队", "law_firm": "所内"}
_SCOPE_BUILTIN = "builtin"
_SCOPE_LAWYER = "lawyer"

#: 用户/共享技能总开关：``flags.py`` 由 CORE lane 提供，未合并时退回读这个环境变量
_USER_SKILLS_ENV = "FACHUAN_AGENT_USER_SKILLS"
#: 不注入提示块的开关取值：``off`` 是回滚、``dry`` 是「与 on 等价但不注入」
_BLOCK_DISABLED_VALUES = frozenset({"off", "dry"})


def render_skill_block(skills: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """渲染索引块，返回 ``(block, not_injected)``；``skills`` 为空或开关关闭 → ``("", [])``。"""
    if not skills or not _prompt_block_enabled():
        return "", []
    header_cost = _used(_HEADER)
    if header_cost >= SKILL_INDEX_BUDGET:
        # 预算连标题都装不下：如实把全部条目标成未注入，而不是注入半截标题
        return "", [_ref(entry) for entry in skills]

    name_costs = [len(_name_line(entry)) + 1 for entry in skills]
    lines: list[str] = list(_HEADER)
    used = header_cost
    reserved = sum(name_costs)
    upgraded = 0
    for index, entry in enumerate(skills):
        reserved -= name_costs[index]
        line = _full_line(entry)
        cost = len(line) + 1
        if used + cost + reserved > SKILL_INDEX_BUDGET:
            # 升级只看优先级前缀：这一条装不下就停，剩下的预算全留给「名字」第二轮
            break
        lines.append(line)
        used += cost
        upgraded += 1

    not_injected: list[dict[str, Any]] = []
    for index in range(upgraded, len(skills)):
        cost = name_costs[index]
        if used + cost > SKILL_INDEX_BUDGET:
            not_injected.append(_ref(skills[index]))
            continue
        lines.append(_name_line(skills[index]))
        used += cost

    if len(lines) == len(_HEADER):
        return "", not_injected
    return "\n".join(lines) + "\n", not_injected


def _used(lines: Sequence[str]) -> int:
    """已占用字数：每行按「行文本 + 1 个换行」计。"""
    return sum(len(line) + 1 for line in lines)


def _full_line(entry: dict[str, Any]) -> str:
    """完整行：``- [所内] contract-review：《合同审查三段式》——审阅合同时使用…``"""
    head = f"- [{_label(entry)}] {_name_of(entry)}：{_title_text(entry)}"
    description = _description_text(entry)
    return f"{head}——{description}" if description else head


def _name_line(entry: dict[str, Any]) -> str:
    """第二轮降级行：只留标签与名字，模型仍可据此调 ``get_agent_skill``。"""
    return f"- [{_label(entry)}] {_name_of(entry)}"


def _title_text(entry: dict[str, Any]) -> str:
    """书名号包裹的显示名；缺失时用 name 兜底，块里不会出现空的 ``《》``。"""
    return f"《{_title_of(entry)}》"


def _title_of(entry: dict[str, Any]) -> str:
    """显示名单行化：标题里有换行会顶掉一条技能的预算，也会破坏块的 markdown 结构。"""
    return re.sub(r"\s+", " ", str(entry.get("title") or "")).strip() or _name_of(entry)


def _description_text(entry: dict[str, Any]) -> str:
    """单行描述：折叠空白后截断到 ``PER_ITEM_DESCRIPTION_MAX`` 字并加 ``…``。

    截断必须留省略号：不留的话律师会以为描述原本就到此为止，改技能时找不出「谁把
    关键信息写在了第 221 个字」。
    """
    single_line = re.sub(r"\s+", " ", str(entry.get("description") or "")).strip()
    if len(single_line) <= PER_ITEM_DESCRIPTION_MAX:
        return single_line
    return single_line[:PER_ITEM_DESCRIPTION_MAX] + "…"


def _label(entry: dict[str, Any]) -> str:
    """作用域中文标签（四档一一对应）。"""
    return _SCOPE_LABELS[_scope_of(entry)]


def _scope_of(entry: dict[str, Any]) -> str:
    """作用域：未知 / 空值按个人处理——不会把来历不明的内容标成所内统一规范。"""
    scope = str(entry.get("scope") or "")
    if scope in _SCOPE_LABELS:
        return scope
    return _SCOPE_BUILTIN if entry.get("source") == "builtin" else _SCOPE_LAWYER


def _name_of(entry: dict[str, Any]) -> str:
    """命令名（``get_agent_skill`` 的入参就是它）。"""
    return str(entry.get("name") or "")


def _ref(entry: dict[str, Any]) -> dict[str, Any]:
    """``not_injected`` 的最小投影：**不带正文**。

    入参条目可能带 32KB 正文（``resolve_for_user`` 的交付面），随提示块回传前端会把
    响应体撑爆，而前端只需要「哪几条没进索引」。
    """
    return {
        "key": str(entry.get("key") or ""),
        "name": _name_of(entry),
        "scope": _scope_of(entry),
        "title": _title_of(entry),
    }


def _prompt_block_enabled() -> bool:
    """索引块开关：``off``（回滚）与 ``dry``（只记日志、不注入）都不注入。

    优先 ``flags.prompt_block_enabled()``（CORE lane 的唯一读法），模块未合并时读环境
    变量，口径与 ``expand`` 的总开关一致：缺省 / 未知取值都按开处理。
    """
    flag = _flag_function("prompt_block_enabled")
    if flag is not None:
        return bool(flag())
    return os.environ.get(_USER_SKILLS_ENV, "").strip().lower() not in _BLOCK_DISABLED_VALUES


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
