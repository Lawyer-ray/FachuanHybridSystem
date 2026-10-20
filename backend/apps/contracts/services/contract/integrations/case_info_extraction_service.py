"""合同文件夹扫描的案件信息提取与回填。

扫描完成后从裁判文书类候选 PDF 提取「审级 / 法院名称 / 案号 / 判决（调解）主文」，
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
    ("执保", "执行"),
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
    if candidate.get("skip_reason"):
        return False
    filename = str(candidate.get("filename") or "")
    if not filename.lower().endswith(".pdf"):
        return False
    return any(kw in filename for kw in JUDGMENT_FILENAME_KEYWORDS)


def extract_case_info_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    storage_provider: Any | None = None,
) -> list[dict[str, Any]]:
    """对裁判文书类候选逐个提取案件信息，单文件失败跳过不影响整体。

    Returns:
        [{"source_path", "filename", "number", "document_name", "court_name", "stage", "content"}, ...]
    """
    from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

    extractor = JudgmentPdfExtractor()
    extractions: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()

    for candidate in candidates:
        if not is_judgment_candidate(candidate):
            continue
        source_path = str(candidate.get("source_path") or "")
        filename = str(candidate.get("filename") or "")
        try:
            result = _extract_pdf(extractor, source_path, storage_provider=storage_provider)
        except Exception:
            logger.warning("case_info_extract_failed", extra={"source_path": source_path}, exc_info=True)
            continue

        number = str(result.number or "").strip()
        if not number:
            logger.info("case_info_skip_no_number", extra={"source_path": source_path})
            continue
        # 同案号多份文书（判决书+送达回证副本等）只保留第一份提取结果
        if number in seen_numbers:
            continue
        seen_numbers.add(number)

        document_name = str(result.document_name or "").strip()
        extractions.append(
            {
                "source_path": source_path,
                "filename": filename,
                "number": number,
                "document_name": document_name,
                "court_name": str(result.court_name or "").strip(),
                "stage": infer_stage(case_number=number, document_name=document_name),
                "content": str(result.content or "").strip(),
            }
        )

    extractions.sort(key=lambda item: item["number"])
    return extractions


def _extract_pdf(extractor: Any, source_path: str, *, storage_provider: Any | None = None) -> Any:
    """本地/云存储 PDF 提取：云存储先落临时文件（提取器按路径读取）。"""
    if storage_provider is None:
        return extractor.extract(source_path)

    file_bytes = storage_provider.read_file(source_path)
    suffix = Path(source_path).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        return extractor.extract(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


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

        case_number = existing_numbers.get(number)
        if case_number is None:
            case_number = CaseNumber.objects.create(
                case=case,
                number=number,
                document_name=str(item.get("document_name") or ""),
                document_content=str(item.get("content") or ""),
            )
            existing_numbers[number] = case_number
            stats["case_numbers_created"] += 1
        else:
            # 只回填空字段：一审案号已有主文时，重复扫描/导入不得覆盖人工维护内容
            changed_fields: list[str] = []
            if not case_number.document_name and item.get("document_name"):
                case_number.document_name = str(item["document_name"])
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
