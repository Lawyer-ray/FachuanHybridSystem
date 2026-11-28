"""把一条技能渲染成物化的 ``SKILL.md``（纯函数，无 IO）。

## frontmatter 是白名单，不是「原样拼接」

只写 ``name`` / ``description`` 两个字段。用户可能提交任意 frontmatter 字段，
其中 ``allowed-tools`` 是 pi 的「实验性预授权工具列表」——放行它等于让技能自己
关掉高危审批，这是本方案的一票否决级细节。其余字段（``metadata`` /
``compatibility`` / ``disable-model-invocation`` 等）对 pi 的行为同样有影响，
一律丢弃。渲染函数是唯一写入点，白名单必须钉在这里，不能靠调用方过滤。

``description`` 用 ``json.dumps(ensure_ascii=False)`` 序列化：冒号、``#``、引号、
换行全部安全，顺手挡掉「换行 + ``---`` 伪造 frontmatter 字段」。
"""

from __future__ import annotations

import json
import re

#: 固定前言：技能是律师个人指示，与所内规范冲突时所内规范优先（共享层接入后的边界）
PREAMBLE = "> 本技能由律师本人编写，属于个人工作习惯；与所内规范冲突时以所内规范为准。"


def render_skill_md(name: str, description: str, body: str) -> str:
    """渲染物化文件全文。**只有 name / description 两个 frontmatter 字段。**"""
    single_line = re.sub(r"\s+", " ", description or "").strip()
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {json.dumps(single_line, ensure_ascii=False)}\n"
        "---\n\n"
        f"{PREAMBLE}\n\n"
        f"{body.strip()}\n"
    )
