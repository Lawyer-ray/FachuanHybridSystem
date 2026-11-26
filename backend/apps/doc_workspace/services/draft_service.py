"""AI 起草：模板为骨，LLM 只填**填不出的槽**。

## 路线裁决：不做「整篇自由生成」

| 路线 | 判定 | 理由 |
|---|---|---|
| 整篇自由生成 | 只在「模板里某一条的展开」这一粒度用 | 格式/编号/必备条款全会漂，客户法务第一眼就不信任 |
| 模板 + 逐槽填充 | **主干** | 模板是律所已经验证过的资产；AI 的每一分自由度都在增加复核成本 |

所以这里的边界写死：**LLM 只能返回值，不能改结构**。模板的段落、编号、样式一律
由渲染器保留，`_assert_skeleton_intact()` 把这条约束变成可测量的断言。

## 空位怎么表示

1. 事实里有 → 直接填（金额、日期这类**绝不交模型**，格式错一次就是事故）；
2. 事实里没有但能推 → LLM 填，**空字符串等于没填**（模型很爱回 `""` 或 `"待定"`）；
3. 还是空的 → 写 `<待填写：槽名>` 占位 + 挂一条**未决项批注**。

未决项批注是这套方案的关键：起草稿必须能回答「这里为什么空着」，否则律师拿到的是
一份看起来完整、实际有 12 个坑的合同。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Callable

from docx import Document

logger = logging.getLogger(__name__)

LLMCaller = Callable[[list[dict[str, str]]], str]

#: docxtpl / Jinja 的槽位：`{{ 名称 }}`
_SLOT_RE = re.compile(r"\{\{\s*([A-Za-z0-9_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*\}\}")
#: 未填槽在成稿里的占位形态（必须**可被 grep**，才好挂批注、也好给律师看）
PENDING_TEMPLATE = "<待填写：{slot}>"

#: 模型常见的「等于没填」的回复。宁可判空去挂批注，也不要把它写进合同。
_NON_ANSWERS = frozenset({"", "待定", "未知", "无", "n/a", "na", "null", "none", "-", "—", "tbd", "todo"})


@dataclass
class DraftResult:
    created: bool
    name: str = ""
    subpath: str = ""
    file_url: str = ""
    filled: dict[str, str] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)
    """未填槽（已转成批注）"""

    slot_fill_rate: float = 0.0
    review_run_id: int | None = None
    reason: str = ""


def extract_slots(template_bytes: bytes) -> list[str]:
    """模板里出现的槽位名（去重、保持出现顺序）。"""
    doc = Document(BytesIO(template_bytes))
    seen: dict[str, None] = {}
    for paragraph in doc.paragraphs:
        for match in _SLOT_RE.finditer(paragraph.text):
            seen.setdefault(match.group(1), None)
    # 表格里的槽位同样要收（付款/金额条款常在表格里）
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for match in _SLOT_RE.finditer(paragraph.text):
                        seen.setdefault(match.group(1), None)
    return list(seen)


def _is_answer(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() not in _NON_ANSWERS


def resolve_slots(
    *,
    slots: list[str],
    facts: dict[str, str],
    caller: LLMCaller | None = None,
) -> tuple[dict[str, str], list[str]]:
    """事实优先，剩下的交 LLM。返回 `(已填值, 仍未填的槽)`。

    **事实里的值优先且不可被覆盖**：金额/日期/当事人这类字段进了 LLM 就有格式
    风险，而它们恰恰是错一个字就出事的字段。
    """
    values: dict[str, str] = {k: str(v) for k, v in facts.items() if _is_answer(v)}
    missing = [s for s in slots if not _is_answer(values.get(s))]
    if not missing or caller is None:
        return values, missing

    prompt = [
        {
            "role": "system",
            "content": (
                "你在为一律所起草文书，需要填写模板里的占位槽。\n"
                "规则：\n"
                "1. 只返回 JSON 对象，键是槽名，值是**最终要写进文书的文本**；\n"
                "2. 只能使用给定事实里能推出的信息，**不许编造**金额、日期、主体名称；\n"
                "3. 确实推不出来的槽，**不要**出现在返回结果里（宁缺毋滥）；\n"
                "4. 不要返回解释、不要返回 markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                "## 已知事实\n"
                + "\n".join(f"- {k}: {v}" for k, v in values.items())
                + "\n\n## 待填槽\n"
                + "\n".join(f"- {s}" for s in missing)
            ),
        },
    ]

    import json

    raw = caller(prompt)
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    obj = re.search(r"\{.*\}", text, re.DOTALL)
    guessed: dict[str, Any] = {}
    if obj:
        try:
            parsed = json.loads(obj.group(0))
            if isinstance(parsed, dict):
                guessed = parsed
        except json.JSONDecodeError:
            logger.warning("槽位填充结果不是合法 JSON，前 200 字：%s", text[:200])

    for slot in missing:
        value = guessed.get(slot)
        if _is_answer(value):
            values[slot] = str(value).strip()
    return values, [s for s in slots if not _is_answer(values.get(s))]


def render(template_bytes: bytes, values: dict[str, str], *, pending: list[str]) -> bytes:
    """渲染成稿。未填槽写成可见占位，**不留空**。

    每个值都先过 `markdown_bold_to_sentinel` + `to_body_text`：起草场景里的值本来就可能是
    多段正文（事实与理由、答辩理由），`\\n` 直接进 docxtpl 只会变成软换行——同一个
    `<w:p>` 内的 `<w:br/>`，第二段起吃不到首行缩进。断段必须走 `\\a`，而 `\\a` 只能由代码
    插入（模型输出里的 `\\a`/`\\f` 会凭空改结构乃至撕页，`to_body_text` 负责剥掉）。
    单行短值（金额、日期）过完仍是它自己，行为不变。
    """
    from docxtpl import DocxTemplate

    from apps.documents.services.placeholders.fallback import SANDBOXED_JINJA_ENV
    from apps.documents.services.placeholders.long_text import (
        apply_bold_sentinels,
        markdown_bold_to_sentinel,
        to_body_text,
    )

    context = dict(values)
    for slot in pending:
        context[slot] = PENDING_TEMPLATE.format(slot=slot)
    body_context = {key: to_body_text(markdown_bold_to_sentinel(str(value))) for key, value in context.items()}

    doc = DocxTemplate(BytesIO(template_bytes))
    doc.render(body_context, jinja_env=SANDBOXED_JINJA_ENV)
    output = BytesIO()
    doc.save(output)
    return apply_bold_sentinels(output.getvalue())


def _paragraph_texts(docx_bytes: bytes) -> list[str]:
    doc = Document(BytesIO(docx_bytes))
    return [p.text for p in doc.paragraphs]


def _assert_skeleton_intact(template_bytes: bytes, rendered_bytes: bytes) -> None:
    """模板骨架不得被改写：不含槽位的段落必须逐字、按序留在成稿里。

    这条约束是「模板是已验证资产」这个前提的可测量形式。LLM 一旦开始改结构
    （重排条款、合并段落、动编号），复核成本会立刻超过它省下的时间。

    **为什么不再要求段落数相等**：长正文槽会合法地把 1 段变成 N 段（正文段落之间用 `\\a`
    断段，见 `services/placeholders/long_text.py`），段落数因此不再是骨架不变量。真正的不变量
    是「模板作者写的那些固定段落一个字都不许变」，所以改成子序列匹配：固定段落只能原样
    出现，**不得减少、不得换序**。代价是固定段落与某段生成正文文字完全相同时会漏判——
    这种巧合比误杀一份 20 段的起诉状低危得多。
    """
    tpl = _paragraph_texts(template_bytes)
    out = _paragraph_texts(rendered_bytes)
    fixed = [(index, text) for index, text in enumerate(tpl) if not _SLOT_RE.search(text)]

    cursor = 0
    for index, before in fixed:
        while cursor < len(out) and out[cursor] != before:
            cursor += 1
        if cursor >= len(out):
            raise RuntimeError(f"起草改动了不含槽位的段落（模板第 {index + 1} 段：{before!r} 在成稿里找不到）")
        cursor += 1


def draft_contract(
    *,
    template_bytes: bytes,
    name: str,
    kind: str = "contract",
    owner_id: int,
    subpath_dir: str = "",
    facts: dict[str, str] | None = None,
    caller: LLMCaller | None = None,
    user: Any = None,
    org_access: Any = None,
    auto_review: bool = True,
    stance: str = "neutral",
    contract_type: str = "",
) -> DraftResult:
    """模板 + 事实 → 成稿 → 落进项目文件夹 → （可选）自动排一轮审查。"""
    from . import review_pipeline, write_service

    slots = extract_slots(template_bytes)
    values, pending = resolve_slots(slots=slots, facts=facts or {}, caller=caller)
    rendered = render(template_bytes, values, pending=pending)
    _assert_skeleton_intact(template_bytes, rendered)

    created = write_service.create_file(
        kind=kind,
        owner_id=owner_id,
        subpath_dir=subpath_dir,
        name=name,
        paragraphs=None,
        markdown="",
        raw_docx=rendered,
        user=user,
        org_access=org_access,
    )
    subpath = created["subpath"]

    # 未决项挂成批注：起草稿必须能回答「这里为什么空着」
    if pending:
        write_service.apply_comments(
            kind=kind,
            owner_id=owner_id,
            subpath=subpath,
            comments=[
                {
                    "selection": PENDING_TEMPLATE.format(slot=slot),
                    "text": f"待确认：{slot}。这一项没有从已知事实里推出来，请补充后再定稿。",
                }
                for slot in pending
            ],
            user=user,
            org_access=org_access,
        )

    review_run_id: int | None = None
    if auto_review:
        run = review_pipeline.create_run(
            kind=kind,
            owner_id=owner_id,
            subpath=subpath,
            stance=stance,
            contract_type=contract_type,
            user=user,
            org_access=org_access,
        )
        review_run_id = run.id

    total = len(slots)
    return DraftResult(
        created=True,
        name=created["name"],
        subpath=subpath,
        file_url=created["file_url"],
        filled={k: v for k, v in values.items() if k in slots},
        pending=pending,
        slot_fill_rate=round((total - len(pending)) / total, 4) if total else 1.0,
        review_run_id=review_run_id,
    )


__all__ = [
    "DraftResult",
    "PENDING_TEMPLATE",
    "draft_contract",
    "extract_slots",
    "render",
    "resolve_slots",
]
