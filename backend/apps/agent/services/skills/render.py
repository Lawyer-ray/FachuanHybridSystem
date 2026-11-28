"""把一条技能渲染成交付文本（纯函数，无 IO）。

## frontmatter 是白名单，不是「原样拼接」

``render_skill_md`` 只写 ``name`` / ``description`` 两个字段。用户可能提交任意
frontmatter 字段，其中 ``allowed-tools`` 是 pi 的「实验性预授权工具列表」——放行它
等于让技能自己关掉高危审批，这是本方案的一票否决级细节。其余字段（``metadata`` /
``compatibility`` / ``disable-model-invocation`` 等）对 pi 的行为同样有影响，一律丢弃。
渲染函数是唯一写入点，白名单必须钉在这里，不能靠调用方过滤。

``description`` 用 ``json.dumps(ensure_ascii=False)`` 序列化：冒号、``#``、引号、
换行全部安全，顺手挡掉「换行 + ``---`` 伪造 frontmatter 字段」。

（``render_skill_md`` 现在只剩管理抽屉的「AI 实际读到什么」预览在用；运行时交付
走 ``render_skill_body``，方案 A 之后不再有任何磁盘物化。）

## 来源声明按作用域动态化

同一段正文在不同作用域下的优先级完全不同：个人技能与所内规范冲突时所内赢，所内
技能则是全所强制。写死一句「个人工作习惯」会让一份所内技能在模型眼里降级成建议，
这是 2026-11 二轮审计点出的问题（原 ``PREAMBLE`` 是硬编码的）。
"""

from __future__ import annotations

import json
import re

from .constants import SCOPE_LABELS

#: 各作用域的来源声明。第一人称不用「我」：这段文字是**给模型读的约束**，
#: 不是律师自述，用「本技能」比用「我」更不容易被模型当成用户口吻复述。
_PREAMBLES: dict[str, str] = {
    "builtin": "> 本技能随系统发布，是内置操作指引；与律师的具体指示冲突时以律师为准。",
    "lawyer": "> 本技能由律师本人编写，属于个人工作习惯；与所内规范冲突时以所内规范为准。",
    "team": "> 本技能由所在团队统一维护，属于团队工作规范；与所内规范冲突时以所内规范为准。",
    "law_firm": "> 本技能属全所统一规范，优先级高于个人与团队技能；与个案判断冲突时请示审批人。",
}

#: 未知作用域的兜底：宁可提示「来源不明」也不要沉默地当成个人习惯
_FALLBACK_PREAMBLE = "> 本技能来源未标注，按个人工作习惯对待；与所内规范冲突时以所内规范为准。"

#: frontmatter 里 description 之后的固定尾巴，让管理抽屉的预览与真实交付可对照
_FRONTMATTER_KEYS = ("name", "description")


def scope_preamble(scope: str) -> str:
    """该作用域的来源声明（单行 markdown 引用块）。"""
    return _PREAMBLES.get(str(scope or ""), _FALLBACK_PREAMBLE)


def scope_label(scope: str) -> str:
    """作用域的中文标签（``[所内]`` 里的那两个字）；未知作用域返回空串。"""
    return SCOPE_LABELS.get(str(scope or ""), "")


def render_skill_body(*, scope: str, name: str, title: str, body: str) -> str:
    """运行时交付正文：来源声明 + 正文（无 frontmatter）。

    由 ``services/skills/expand.py``（``/skill:`` 展开）与
    ``/skills/resolve/{ref}/content``（MCP 按需读取）**共用**，保证「点名展开」
    与「自主读取」交给模型的是同一段文字——两处各渲染一次必然漂移。

    ``name`` / ``title`` 目前不写进正文：用途是将来做审计留痕，参数先留在这里，
    避免以后改签名要动所有调用点。
    """
    del name, title  # 见 docstring：保留参数是为了未来审计留痕
    cleaned = (body or "").strip()
    return f"{scope_preamble(scope)}\n\n{cleaned}\n"


def render_skill_md(name: str, description: str, body: str, *, scope: str = "lawyer") -> str:
    """渲染 ``SKILL.md`` 全文（管理抽屉预览用）。**只有 name / description 两个字段。**"""
    single_line = re.sub(r"\s+", " ", description or "").strip()
    return (
        "---\n"
        f"{_FRONTMATTER_KEYS[0]}: {name}\n"
        f"{_FRONTMATTER_KEYS[1]}: {json.dumps(single_line, ensure_ascii=False)}\n"
        "---\n\n"
        f"{scope_preamble(scope)}\n\n"
        f"{(body or '').strip()}\n"
    )
