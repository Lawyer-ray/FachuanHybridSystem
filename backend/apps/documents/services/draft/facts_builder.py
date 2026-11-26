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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.apps import apps

from apps.core.models.enums import AuthorityType, LegalStatus

logger = logging.getLogger(__name__)

#: 单份材料拼进事实的字符上限：整篇塞进去只会让模型在最不重要的段落上烧完上下文
MATERIAL_EXCERPT_CHARS = 2000
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
    return facts


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
    """按文件名把案件材料的解析 Markdown 拼成一段素材；取不到就返回空串。

    待办（归案 bind 时补）：把解析任务 id 写到材料上（新增字段 + 迁移），再改成按 id 精确
    取。**在此之前不做要素抽取**——按文件名匹配本身就不够可靠，据此抽取事实等于凭空补量。
    """
    filenames = _material_filenames(case)
    if not filenames:
        return ""
    task_model = apps.get_model("document_parsing", "DocumentParsingTask")
    parts: list[str] = []
    for filename in filenames:
        task = (
            task_model.objects.filter(status=task_model.Status.COMPLETED, file_name=filename)
            .only("file_name", "markdown")
            .order_by("-completed_at")
            .first()
        )
        if task is None or not _text(task.markdown):
            continue
        parts.append(f"### {filename}\n{task.markdown[:MATERIAL_EXCERPT_CHARS]}")
        if len(parts) >= MATERIAL_LIMIT:
            break
    return "\n\n".join(parts)


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
