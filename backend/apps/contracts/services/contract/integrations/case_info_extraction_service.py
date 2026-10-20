"""合同文件夹扫描的案件信息提取与回填。

扫描完成后从候选 PDF 提取「审级 / 法院名称 / 案号 / 判决（调解）主文」：
裁判文书（判决书/调解书等）完整提取；法院程序性文书（告知书/通知书等）只提取
案号与审理机构（执行等阶段的案号常只在程序性文书里，无裁判主文）。
确认导入时**追加式**写入合同关联案件：每份文书对应一条 CaseNumber（按案号去重
upsert、已有内容不覆盖）+ 一条审理机构记录，多阶段（一审、二审、执行……）共存，
{{案件案号}}/{{管辖法院}}/{{案件审理结果}} 归档占位符天然拼接全部阶段。
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 视为裁判文书的文件名关键词。
# 普通程序性"裁定书"（保全/管辖等）通常无最终结果主文且与一审案号同号重复，不参与提取。
JUDGMENT_FILENAME_KEYWORDS: tuple[str, ...] = (
    "判决书",
    "调解书",
    "仲裁裁决书",
    "执行证书",
    "执行裁定书",
    "终本裁定",
)

# 法院程序性文书关键词：只提取案号/审理机构（无主文）——
# 执行等阶段的案号常只出现在告知书/通知书里，文书本身没有裁判主文
COURT_NOTICE_FILENAME_KEYWORDS: tuple[str, ...] = (
    "告知书",
    "通知书",
    "传票",
    "决定书",
)

# 案号类型字 → 审级。按"具体在前、泛化在后"排列（如"执保"在"执"之前），
# contains 命中即取首个，保证多字类型字优先于单字
_STAGE_FROM_CASE_NUMBER: tuple[tuple[str, str], ...] = (
    ("民初", "一审"),
    ("刑初", "一审"),
    ("行初", "一审"),
    ("知初", "一审"),
    ("民终", "二审"),
    ("刑终", "二审"),
    ("行终", "二审"),
    ("知终", "二审"),
    ("财保", "保全"),
    ("执保", "保全"),
    ("执", "执行"),
    ("再", "再审"),
    ("监", "再审"),
    ("破", "破产"),
)

_STAGE_FROM_DOCUMENT_NAME: tuple[tuple[str, str], ...] = (
    ("执行", "执行"),
    ("终本", "执行"),
    ("再审", "再审"),
)

# 执行类程序性文书（执行告知书等）的执行结果摘要线索词
# 款项句：含金额且带发放/到位语义（裸"扣划/冻结"多出现在保全段落，不作为款项句依据）
_ENFORCE_DISBURSEMENT_HINTS: tuple[str, ...] = ("已支付", "发放", "余款", "执行款", "案款")
# 状态句：按重要性分两档（终结执行/终本 是执行程序的最终结论）
_ENFORCE_FINAL_STATUS_HINTS: tuple[str, ...] = ("终结执行", "终本")
_ENFORCE_PROGRESS_STATUS_HINTS: tuple[str, ...] = ("尚未全部执行到位", "限制其高消费", "限制高消费", "失信")

# 保全类案号类型字（诉前财保/执保/诉讼民保等）是程序性保全编号，
# 不属于阶段主案号，不纳入案件信息提取
_PRESERVATION_NUMBER_KEYWORDS: tuple[str, ...] = ("财保", "执保", "民保", "行保")


def is_preservation_number(number: str) -> bool:
    """案号是否为保全类程序编号（财保/执保/民保/行保）。"""
    return any(kw in str(number or "") for kw in _PRESERVATION_NUMBER_KEYWORDS)


def infer_stage(*, case_number: str = "", document_name: str = "") -> str:
    """从案号类型字 / 文书名称推断审级（一审、二审、执行、再审…），无法推断返回空串。"""
    number = str(case_number or "")
    if number:
        matched = [stage for code, stage in _STAGE_FROM_CASE_NUMBER if code in number]
        if matched:
            return matched[0]

    name = str(document_name or "")
    for keyword, stage in _STAGE_FROM_DOCUMENT_NAME:
        if keyword in name:
            return stage
    return ""


def is_judgment_candidate(candidate: dict[str, Any]) -> bool:
    """候选是否为裁判文书类文件（按文件名关键词判断，非跳过、PDF）。"""
    return _match_filename_keyword(candidate, JUDGMENT_FILENAME_KEYWORDS) is not None


def is_court_notice_candidate(candidate: dict[str, Any]) -> bool:
    """候选是否为法院程序性文书（告知书/通知书等，只提取案号不要求主文）。"""
    return _match_filename_keyword(candidate, COURT_NOTICE_FILENAME_KEYWORDS) is not None


def _match_filename_keyword(candidate: dict[str, Any], keywords: tuple[str, ...]) -> str | None:
    """按文件名关键词分类候选，命中返回关键词，非 PDF 或已跳过返回 None。"""
    if candidate.get("skip_reason"):
        return None
    filename = str(candidate.get("filename") or "")
    if not filename.lower().endswith(".pdf"):
        return None
    for keyword in keywords:
        if keyword in filename:
            return keyword
    return None


def extract_case_info_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    storage_provider: Any | None = None,
) -> list[dict[str, Any]]:
    """对裁判文书 + 法院程序性文书候选逐个提取案件信息，单文件失败跳过不影响整体。

    两层提取：
    - 裁判文书（判决书/调解书等）：完整提取案号/文书名/法院/主文；
    - 法院程序性文书（告知书/通知书等）：只提取案号/法院——执行等阶段的案号
      常只在程序性文书里出现；其中执行阶段的文书会提炼执行结果摘要
      （扣划发放金额、终结执行等）作为该案号的内容。
    同案号多份文书时优先保留带主文的那份（判决书 > 受理通知书）。

    Returns:
        [{"source_path", "filename", "number", "document_name", "court_name", "stage", "content"}, ...]
    """
    from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

    extractor = JudgmentPdfExtractor()
    by_number: dict[str, dict[str, Any]] = {}

    for candidate in candidates:
        judgment_kw = _match_filename_keyword(candidate, JUDGMENT_FILENAME_KEYWORDS)
        notice_kw = _match_filename_keyword(candidate, COURT_NOTICE_FILENAME_KEYWORDS)
        if judgment_kw is None and notice_kw is None:
            continue

        source_path = str(candidate.get("source_path") or "")
        filename = str(candidate.get("filename") or "")
        try:
            if judgment_kw is not None:
                result = _extract_pdf(extractor, source_path, mode="judgment", storage_provider=storage_provider)
                document_name = str(result.document_name or "").strip()
            else:
                result = _extract_pdf(
                    extractor,
                    source_path,
                    mode="reference",
                    storage_provider=storage_provider,
                    include_full_text=True,
                )
                # 程序性文书的文书名一律取文件名关键词：正文中提到的"民事裁定书"等
                # 是引用而非本文书名，提取器按全文匹配会误报
                document_name = notice_kw or ""
        except Exception:
            logger.warning("case_info_extract_failed", extra={"source_path": source_path}, exc_info=True)
            continue

        number = str(result.number or "").strip()
        if not number:
            logger.info("case_info_skip_no_number", extra={"source_path": source_path})
            continue
        if is_preservation_number(number):
            logger.info("case_info_skip_preservation_number", extra={"number": number})
            continue

        stage = infer_stage(case_number=number, document_name=document_name)
        content = str(result.content or "").strip()
        if notice_kw is not None and stage == "执行" and not content:
            # 执行阶段的程序性文书（执行告知书等）没有裁判主文，但正文常含
            # 实质执行结果（扣划发放金额、终结执行等），提炼摘要充当该案号的结果内容
            content = _summarize_enforcement_notice(str(getattr(result, "full_text", None) or ""))

        item = {
            "source_path": source_path,
            "filename": filename,
            "number": number,
            "document_name": document_name,
            "court_name": str(result.court_name or "").strip(),
            "stage": stage,
            "content": content,
        }
        existing = by_number.get(number)
        # 同案号优先保留带主文的提取（判决书/调解书优先于受理通知书等）
        if existing is None or (not existing.get("content") and item.get("content")):
            by_number[number] = item

    extractions = sorted(by_number.values(), key=lambda item: item["number"])
    return extractions


def _extract_pdf(
    extractor: Any,
    source_path: str,
    *,
    mode: str = "judgment",
    storage_provider: Any | None = None,
    include_full_text: bool = False,
) -> Any:
    """本地/云存储 PDF 提取：云存储先落临时文件（提取器按路径读取）。

    mode="judgment" 要求裁判主文；mode="reference" 只取案号/法院（程序性文书），
    include_full_text=True 时附带文书全文供上层摘要。
    """
    target = source_path
    tmp_path: str | None = None
    if storage_provider is not None:
        file_bytes = storage_provider.read_file(source_path)
        suffix = Path(source_path).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        target = tmp_path

    try:
        if mode == "reference":
            return extractor.extract_case_reference(target, include_full_text=include_full_text)
        return extractor.extract(target)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def _summarize_enforcement_notice(text: str) -> str:
    """从执行阶段程序性文书正文提炼执行结果摘要。

    规则（按文书原句拼接，最多三句）：
    - 款项句：含金额且带发放/到位语义（已支付/发放/余款/执行款/案款）——
      保全段落里"冻结…（扣划该账户N元）"没有发放语义，不会误选；
    - 状态句：终结执行/终本优先，其次尚未到位/限制高消费/失信。
    无任何命中返回空串（上层按无内容处理）。
    """
    normalized = re.sub(r"\s+", "", str(text or ""))
    if not normalized:
        return ""

    sentences = [s for s in re.split(r"[。；;]", normalized) if s]
    picked: dict[int, str] = {}
    for idx, sentence in enumerate(sentences):
        if "元" in sentence and any(hint in sentence for hint in _ENFORCE_DISBURSEMENT_HINTS):
            picked[idx] = sentence
            break

    status_sentences = [
        (idx, s)
        for idx, s in enumerate(sentences)
        if idx not in picked
        and (any(h in s for h in _ENFORCE_FINAL_STATUS_HINTS) or any(h in s for h in _ENFORCE_PROGRESS_STATUS_HINTS))
    ]
    # 终结执行/终本（最终结论）优先于进度类状态，展示时仍按文书原句顺序
    status_sentences.sort(key=lambda pair: 0 if any(h in pair[1] for h in _ENFORCE_FINAL_STATUS_HINTS) else 1)
    for idx, sentence in status_sentences[: 3 - len(picked)]:
        picked[idx] = sentence

    if not picked:
        return ""
    summary = "。".join(_trim_notice_sentence(picked[idx]) for idx in sorted(picked)) + "。"
    return summary[:200]


def _trim_notice_sentence(sentence: str, limit: int = 90) -> str:
    """超长句在逗号边界截断，避免告知书的告知义务条款淹没关键结论。"""
    if len(sentence) <= limit:
        return sentence
    cut = sentence.rfind("，", 0, limit)
    if cut <= 0:
        return sentence[:limit] + "…"
    return sentence[:cut] + "…"


def apply_case_info_to_contract(
    contract: Any,
    extractions: list[dict[str, Any]],
    *,
    selected_paths: set[str] | None = None,
) -> dict[str, Any]:
    """将提取的案件信息追加式写入合同关联案件。

    多阶段共存策略：
    - 案号按 (case, number) 去重 upsert，**绝不删除**已有案号；
    - 文书名称/主文仅在为空时回填，已有内容（含人工编辑）不覆盖；
    - 审理机构按 (case, authority_type="trial", name) 去重新增，多法院共存；
    - 合同尚无案件时自动创建一条（名称同合同），保证归档占位符可用。
    """
    from apps.cases.models import Case, CaseNumber, SupervisingAuthority

    selected = selected_paths if selected_paths is not None else {str(e.get("source_path") or "") for e in extractions}
    applicable = [e for e in extractions if str(e.get("source_path") or "") in selected and e.get("number")]
    stats: dict[str, Any] = {
        "case_id": None,
        "case_created": False,
        "case_numbers_created": 0,
        "case_numbers_filled": 0,
        "courts_created": 0,
    }
    if not applicable:
        return stats

    case = Case.objects.filter(contract_id=contract.id).order_by("id").first()
    if case is None:
        case = Case.objects.create(
            contract_id=contract.id,
            name=str(contract.name or "")[:255] or f"合同-{contract.id}",
            case_type=_map_case_type(getattr(contract, "case_type", "")),
        )
        stats["case_created"] = True
        logger.info("case_info_auto_created_case", extra={"contract_id": contract.id, "case_id": case.id})
    stats["case_id"] = case.id

    existing_numbers = {
        str(cn.number): cn
        for cn in CaseNumber.objects.filter(case=case).only("id", "number", "document_name", "document_content")
    }

    for item in applicable:
        number = str(item["number"])
        court_name = str(item.get("court_name") or "").strip()
        # 程序性文书无内容时文书名不落库，留给将来扫到的真裁判文书；
        # 执行阶段告知书提炼出的执行结果摘要视同内容，文书名一并落库
        document_name = str(item.get("document_name") or "") if item.get("content") else ""

        case_number = existing_numbers.get(number)
        if case_number is None:
            case_number = CaseNumber.objects.create(
                case=case,
                number=number,
                document_name=document_name,
                document_content=str(item.get("content") or ""),
            )
            existing_numbers[number] = case_number
            stats["case_numbers_created"] += 1
        else:
            # 只回填空字段：一审案号已有主文时，重复扫描/导入不得覆盖人工维护内容
            changed_fields: list[str] = []
            if document_name and not case_number.document_name:
                case_number.document_name = document_name
                changed_fields.append("document_name")
            if not case_number.document_content and item.get("content"):
                case_number.document_content = str(item["content"])
                changed_fields.append("document_content")
            if changed_fields:
                case_number.save(update_fields=changed_fields)
                stats["case_numbers_filled"] += 1

        if court_name and not _court_exists(case, court_name):
            SupervisingAuthority.objects.create(case=case, authority_type="trial", name=court_name)
            stats["courts_created"] += 1

    return stats


def _court_exists(case: Any, court_name: str) -> bool:
    """同案件是否已有该审理机构。

    全称/简称视为同一家（"广东省东莞市第三人民法院" 与 "东莞市第三人民法院"
    互为后缀），避免重复扫描或人工先录简称时建出重复法院。
    """
    from apps.cases.models import SupervisingAuthority

    for name in SupervisingAuthority.objects.filter(case=case, authority_type="trial").values_list("name", flat=True):
        existing = str(name or "").strip()
        if not existing:
            continue
        if existing == court_name or existing.endswith(court_name) or court_name.endswith(existing):
            return True
    return False


def _map_case_type(contract_case_type: str) -> str:
    """合同案件类型 → 案件 SimpleCaseType（未匹配回落民事）。"""
    mapping = {
        "civil": "civil",
        "administrative": "administrative",
        "criminal": "criminal",
    }
    value = re.sub(r"\s+", "", str(contract_case_type or ""))
    return mapping.get(value, "civil")
