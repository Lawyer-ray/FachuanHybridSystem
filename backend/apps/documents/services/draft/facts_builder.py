"""起草前的事实组装：调用方显式给 > 案件/合同实体字段 > 材料 Markdown 摘要。

## 为什么金额/日期只从实体取
金额、日期错一个字符就是一份要重签的文书，而模型推不出来时只会编。所以这类字段
只认案件/合同上的真实字段，取不到就不进 facts —— 让解析器把它留在未决项里，
比让模型「补一个看起来合理的数」安全得多。

## 材料 Markdown 为什么只拼摘要
材料与解析结果之间没有显式关联，唯一可用的连接是文件名（见 `_material_markdown`）。
文件名会撞、解析任务可能是旧版本，靠它做要素抽取（金额/日期/当事人）等于猜；
这一版只把 Markdown 截一段拼成素材喂给模型，要素抽取等功能有显式关联后再做。
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.apps import apps

from apps.core.models.enums import AuthorityType, LegalStatus

logger = logging.getLogger(__name__)

#: 单份材料拼进事实的字符上限：整篇塞进去只会让模型在最不重要的段落上烧完上下文
MATERIAL_EXCERPT_CHARS = 2000

#: 摘录口径：**头部 + 关键条款行**。
#: 真机（14 页土地分包合同）实测：只截前 2000 字时，模型看到的正好是合同首部与面积，
#: 承包金 384,277、滞纳金 3‰、第九条解除/没收保证金全在截断之外 —— 成稿于是写成
#: 「金额以合同约定为准」「合同名称以原件为准」这种空话，一份能用的起诉状变成模板。
#: 关键词行的窗口各自带上下文，保证「条款 + 金额 + 期限」落在同一段里。
MATERIAL_HEAD_CHARS = 600
#: 关键词窗口前后各取多少字（够放下「条款号 + 内容」一整句）
MATERIAL_WINDOW_CHARS = 220
#: 最多收集多少个关键词窗口
MATERIAL_KEYWORD_HITS = 14

#: 起草真正要用的条款线索：费用与到期、违约与解除、保证金、管辖与送达
MATERIAL_KEYWORDS: tuple[str, ...] = (
    "承包金",
    "租金",
    "管理维护费",
    "水费",
    "保证金",
    "押金",
    "违约金",
    "滞纳金",
    "解除",
    "终止",
    "管辖",
    "争议",
    "送达",
    "期限",
)
#: 一份文书最多拼几份材料，按材料在案件里的登记顺序取前 N 份
MATERIAL_LIMIT = 3
#: 材料摘要落在 facts 里的键：它不是骨架占位符，只作为模型素材
MATERIAL_FACTS_KEY = "材料摘要"


def build_facts(
    *,
    case: Any = None,
    contract: Any = None,
    explicit: dict[str, str] | None = None,
) -> dict[str, str]:
    """组装起草用的事实字典（空值不入字典，缺的键由解析器计入未决项）。

    Args:
        case: 案件实体，可为 None；只做属性读，不写库
        contract: 合同实体，可为 None
        explicit: 调用方显式给出的事实，优先级最高（律师口述 > 系统里存的）

    Returns:
        键为中文事实名；与骨架占位符同名的键会被解析器直接填进文档
    """
    facts: dict[str, str] = {}
    material_excerpt = _material_markdown(case)
    if material_excerpt:
        facts[MATERIAL_FACTS_KEY] = material_excerpt

    for source in (_case_facts(case), _contract_facts(contract)):
        for key, value in source.items():
            facts.setdefault(key, value)

    # 显式事实最后覆盖：同一个键，律师说的算
    for key, value in (explicit or {}).items():
        text = _text(value)
        if text:
            facts[str(key)] = text
    return _reconcile_amounts(facts)


#: 材料里「合计/共计/总计 … 元」的口径，用来跟案件登记的涉案金额对账
_TOTAL_RE = re.compile(r"(?:合计|共计|总计)[^\d]{0,8}(?P<amount>\d[\d,，]*(?:\.\d+)?)\s*元")


def _reconcile_amounts(facts: dict[str, str]) -> dict[str, str]:
    """案件字段与材料合计不一致时，**不把两套数字并列喂给模型**。

    真机（案卷 489）：案件登记的涉案金额是 440,000，律师函与合同算出来的欠款合计是
    404,221。两个数字一起进提示词后，模型两次写成「欠付承包金本金 440,000 元」——
    起诉状里出现一个材料里根本不存在的金额，是最危险的一类错。

    处置：**去掉案件字段**（它只是登记值，不是诉请），改喂一条口径提示，让模型以材料为准，
    并把差额留给律师核对。
    """
    material = facts.get(MATERIAL_FACTS_KEY, "")
    registered = facts.get("涉案金额", "")
    if not material or not registered:
        return facts
    totals = {_normalize_amount(m.group("amount")) for m in _TOTAL_RE.finditer(material)}
    totals.discard("")
    if not totals or _normalize_amount(registered) in totals:
        return facts
    reconciled = dict(facts)
    reconciled.pop("涉案金额", None)
    # **只摘掉，不补一句「以材料为准」**：真机试过把口径提示喂进去，模型转头把材料合计
    # 当成又一个欠款项目，写出「合计 796,845 元，其中承包金 384,277 + 应付款 404,221」。
    # 材料本身已经写清分项与合计，模型只要看不到第二个数就不会去凑。
    logger.warning("口径冲突：案件登记涉案金额=%s 材料合计=%s，已不喂登记值", registered, sorted(totals))
    return reconciled


def _normalize_amount(value: Any) -> str:
    text = str(value or "").replace(",", "").replace("，", "").strip()
    try:
        return str(Decimal(text).normalize())
    except (InvalidOperation, ValueError):
        return ""


def _case_facts(case: Any) -> dict[str, str]:
    if case is None:
        return {}
    facts = {
        "原告": _party_name(case, LegalStatus.PLAINTIFF),
        "被告": _party_name(case, LegalStatus.DEFENDANT),
        "案由": _text(getattr(case, "cause_of_action", "")),
        "案号": _case_number(case),
        "涉案金额": _money(getattr(case, "target_amount", None)),
        "审理机构": _trial_authority(case),
        "收案日期": _date(getattr(case, "start_date", None)),
    }
    return {key: value for key, value in facts.items() if value}


def _contract_facts(contract: Any) -> dict[str, str]:
    if contract is None:
        return {}
    facts = {
        "合同名称": _text(getattr(contract, "name", "")),
        "合同开始日期": _date(getattr(contract, "start_date", None)),
        "合同结束日期": _date(getattr(contract, "end_date", None)),
        "指定日期": _date(getattr(contract, "specified_date", None)),
    }
    return {key: value for key, value in facts.items() if value}


def _party_name(case: Any, legal_status: str) -> str:
    """按诉讼地位取当事人名称（当事人是我们系统里唯一权威的来源）。"""
    parties = getattr(case, "parties", None)
    if parties is None:
        return ""
    for party in parties.all():
        if party.legal_status != legal_status:
            continue
        return _text(getattr(party.client, "name", ""))
    return ""


def _case_number(case: Any) -> str:
    """案号：优先已生效那条（一个案件会同时挂着多份文书的案号）。"""
    numbers = getattr(case, "case_numbers", None)
    if numbers is None:
        return ""
    active = numbers.filter(is_active=True).first()
    if active is not None:
        return _text(active.number)
    first = numbers.first()
    return _text(first.number) if first is not None else ""


def _trial_authority(case: Any) -> str:
    """审理机构：主管机关里性质为「审理机构」的那一条。"""
    authorities = getattr(case, "supervising_authorities", None)
    if authorities is None:
        return ""
    for authority in authorities.all():
        if authority.authority_type == AuthorityType.TRIAL:
            return _text(authority.name)
    return ""


def _material_markdown(case: Any) -> str:
    """把案件材料的解析结果拼成一段素材；取不到就返回空串。

    **两条口径，按可信度从高到低**：

    1. `CaseMaterial.parsing_task`（归案时登记的那次解析）——精确到「这条材料」，
       文件名撞了也不会串；
    2. 退回按原始文件名匹配 `DocumentParsingTask`——历史数据没有 FK，不能因此丢掉。

    **为什么 markdown 空了要退回 text**：`markdown` 不是每个后端都产——DeepSeek OCR 只写
    `text`（`ParsedDocument.markdown` 为 None），MinerU 也实测有 35/84 条完成任务 markdown
    为空。只读 markdown 的写法会让这些材料**静默缺席**起草提示词，表现为「模型没看到合同」
    而没有任何报错（真机基线 D2，见 docs/analysis/legal-doc-generation-2026-11-26/07）。
    """
    materials = _materials_of(case)
    if materials is None:
        return ""
    task_model = apps.get_model("document_parsing", "DocumentParsingTask")
    parts: list[str] = []
    for material in materials:
        excerpt = _linked_excerpt(material, task_model=task_model) or _filename_excerpt(material, task_model=task_model)
        if not excerpt:
            continue
        parts.append(excerpt)
        if len(parts) >= MATERIAL_LIMIT:
            break
    return "\n\n".join(parts)


def _materials_of(case: Any) -> Any:
    """材料的可迭代对象。

    **为什么要按 id 回查**：起草链传进来的是 `CaseDTO`（带行级 ACL 的只读视图），
    它按设计**不带材料**。只认 `case.materials` 的话，材料在库里也永远进不了提示词——
    真机就是这么静默丢掉整份合同的（模型只看到案件字段，于是写「金额以合同约定为准」）。
    """
    materials = getattr(case, "materials", None)
    if materials is not None:
        return (
            materials.select_related("source_attachment", "parsing_task")
            if hasattr(materials, "select_related")
            else materials
        )
    case_id = getattr(case, "id", None)
    if not case_id:
        return None
    from apps.cases.models.material import CaseMaterial

    return CaseMaterial.objects.filter(case_id=case_id).select_related("source_attachment", "parsing_task")


def _linked_excerpt(material: Any, *, task_model: Any) -> str:
    """优先用归案时绑定的那次解析（`parsing_task` FK）。"""
    task = getattr(material, "parsing_task", None)
    if task is None or getattr(task, "status", "") != task_model.Status.COMPLETED:
        return ""
    body = _text(task.markdown) or _text(task.text)
    if not body:
        return ""
    name = _attachment_name(material) or task.file_name
    return f"### {name}\n{_excerpt(body)}"


def _filename_excerpt(material: Any, *, task_model: Any) -> str:
    """历史口径：按原始文件名找最近一条完成任务（没有 FK 的存量数据只能这样）。"""
    name = _attachment_name(material)
    if not name:
        return ""
    task = (
        task_model.objects.filter(status=task_model.Status.COMPLETED, file_name=name)
        .only("file_name", "markdown", "text")
        .order_by("-completed_at")
        .first()
    )
    if task is None:
        return ""
    body = _text(task.markdown) or _text(task.text)
    if not body:
        return ""
    return f"### {name}\n{_excerpt(body)}"


def _excerpt(text: str) -> str:
    """头部 + 关键条款窗口，拼成一份「能用来写文书」的摘录。

    只截头部会漏掉全部条款（真机：承包金/滞纳金/解除条款都在 2000 字之后）；
    全文塞进去又会让模型在最不重要的段落上烧完上下文。所以按**起草要用的线索**取窗口，
    去重后按原文顺序拼接，总长仍受 `MATERIAL_EXCERPT_CHARS` 约束。
    """
    body = text or ""
    if len(body) <= MATERIAL_EXCERPT_CHARS:
        return body
    head = body[:MATERIAL_HEAD_CHARS]
    windows: list[str] = []
    seen: set[int] = set()
    for keyword in MATERIAL_KEYWORDS:
        start = body.find(keyword, MATERIAL_HEAD_CHARS)
        if start < 0:
            continue
        # 同一个位置被多个关键词命中时只取一次（「承包金管理维护费」这类连写）
        bucket = start // MATERIAL_WINDOW_CHARS
        if bucket in seen:
            continue
        seen.add(bucket)
        left = max(MATERIAL_HEAD_CHARS, start - MATERIAL_WINDOW_CHARS)
        windows.append(body[left : start + MATERIAL_WINDOW_CHARS])
        if len(windows) >= MATERIAL_KEYWORD_HITS:
            break
    if not windows:
        return body[:MATERIAL_EXCERPT_CHARS]
    joined = head + "\n……\n" + "\n……\n".join(windows)
    return joined[:MATERIAL_EXCERPT_CHARS]


def _attachment_name(material: Any) -> str:
    attachment = getattr(material, "source_attachment", None)
    if attachment is None:
        return ""
    return _text(attachment.original_filename) or Path(attachment.file.name).name


def _material_filenames(case: Any) -> list[str]:
    """材料附件原始文件名（去重、保持登记顺序）。"""
    materials = getattr(case, "materials", None)
    if materials is None:
        return []
    filenames: list[str] = []
    for material in materials.select_related("source_attachment"):
        attachment = material.source_attachment
        if attachment is None:
            continue
        name = _text(attachment.original_filename) or Path(attachment.file.name).name
        if name and name not in filenames:
            filenames.append(name)
    return filenames


def _money(value: Any) -> str:
    """金额统一成两位小数；**解析不了就返回空串**（= 缺失 → 走未决项），绝不抛。

    为什么参数不收窄成 `Decimal`：真实调用方传进来的是 **DTO**，里面的金额字段是字符串
    （`CaseDTO.target_amount` 来自 `DecimalField` 但已经过 DTO 序列化）。真机联调时
    `f"{value:.2f}"` 直接 `ValueError` 把整个起草打成 500，而单测的 fixture 是 float，
    所以一直没暴露。

    宁可空着让人补，也不要把「解析了一半的字符串」写进起诉状的金额栏。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, (int, float)):
        amount = Decimal(str(value))
    else:
        cleaned = str(value).strip()
        for token in (",", "，", "¥", "￥", "元", " "):
            cleaned = cleaned.replace(token, "")
        try:
            amount = Decimal(cleaned)
        except (InvalidOperation, ValueError, TypeError):
            logger.warning("金额字段无法解析成数字，按缺失处理（进未决项）: %r", value)
            return ""
    return f"{amount:.2f}"


def _date(value: Any) -> str:
    """实体日期按 ISO 写（2026-11-26）：中文年月日的排版是文书格式的事，不是事实的事。

    与 `_money` 同一类坑：DTO 里的日期是字符串，`value.isoformat()` 会直接 AttributeError。
    字符串原样返回（已经是 ISO 就正好，是中文日期也不算错别字，交给排版层）；解析不了的
    对象一律返回空串，让它进未决项。
    """
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value).strip()
    return text


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = ["MATERIAL_EXCERPT_CHARS", "MATERIAL_FACTS_KEY", "MATERIAL_LIMIT", "build_facts"]
