"""立案合同附件：来源解析（三级）与拖拽暂存。

来源优先级（resolve_filing_attachments）：
① 合同最新「合同正本」归档材料（拖拽上传的文件即落成它）
② 合同绑定文件夹中的合同文件（本地/云存储，pdf 优先于 docx、同名多版本取最新）
③ 都没有 → 空列表（立案不上传附件，维持现状）

暂存（stage_filing_attachment）：把拖拽的合同文件保存为
FinalizedMaterial(category=contract_original)，同时满足 Material-first
（不造临时文件区）与归档清单「委托合同」材料需求。
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from django.core.files.storage import default_storage

logger = logging.getLogger("apps.oa_filing.filing_attachment")

_CONTRACT_PDF_SUFFIXES = (".pdf", ".docx", ".doc")

# 合同区文件夹段：去掉编号前缀后以「合同」开头的段（1-合同 / 合同发票 / 合同及发票）。
# 必须按段前缀判定而不是整路径子串——案由目录名（如「…借款合同纠纷一案」）
# 本身含"合同"，整路径匹配会把委托材料下的执业证等误判进合同区（实测 373）。
_ZONE_SEGMENT_PREFIX = "合同"
_NUMBER_PREFIX_RE = re.compile(r"^[\d]+[\s.\-_]*[\)）]?\s*")
# 区域外的强文件名关键词（案名含"合同纠纷"等案由时一律不算，先排除再匹配）
_STRONG_FILENAME_KEYWORDS = (
    "委托合同",
    "委托代理合同",
    "委托协议",
    "服务合同",
    "法律顾问",
    "专项法律事务",
    "合同正本",
    "框架合同",
    "风险告知书",
)
_FALSE_POSITIVE_PATTERNS = ("合同纠纷", "协议纠纷", "合同争议", "协议争议")
# 合同区内仍应排除的文件名关键词（监督卡/补充协议/发票等非正本文书）
_ZONE_EXCLUDE_KEYWORDS = (
    "监督卡",
    "补充协议",
    "补充合同",
    "变更协议",
    "续签协议",
    "发票",
    "专票",
    "普票",
    "开票",
    "invoice",
)


def resolve_filing_attachments(contract_id: int) -> list[str]:  # pragma: no cover
    """解析立案用合同附件的本地文件路径（0 或 1 个）。"""
    material_path = _latest_contract_original_material_path(contract_id)
    if material_path:
        logger.info("立案附件来源=归档材料: contract=%s path=%s", contract_id, Path(material_path).name)
        return [material_path]

    folder_path = _latest_contract_file_from_binding(contract_id)
    if folder_path:
        logger.info("立案附件来源=绑定文件夹: contract=%s path=%s", contract_id, Path(folder_path).name)
        return [folder_path]

    logger.info("立案附件来源=无: contract=%s（不上传附件）", contract_id)
    return []


def _latest_contract_original_material_path(contract_id: int) -> str | None:  # pragma: no cover
    """最新合同正本材料的媒体文件绝对路径；不存在或文件丢失返回 None。"""
    from django.apps import apps as django_apps

    material_model = django_apps.get_model("contracts", "FinalizedMaterial")
    material = (
        material_model.objects.filter(contract_id=contract_id, category="contract_original")
        .order_by("-uploaded_at", "-id")
        .first()
    )
    if material is None or not material.file_path:
        return None
    try:
        abs_path = Path(str(default_storage.path(material.file_path)))
    except (NotImplementedError, ValueError):
        return None
    if not abs_path.is_file():
        logger.warning("立案附件材料文件丢失: contract=%s path=%s", contract_id, material.file_path)
        return None
    return abs_path.as_posix()


def _latest_contract_file_from_binding(contract_id: int) -> str | None:  # pragma: no cover
    """绑定文件夹中最新合同文件的本地路径（pdf 优先、同名多版本取最新）。

    云存储绑定的命中文件下载为本地临时文件（调用方无需关心存储类型）。
    """
    from django.apps import apps as django_apps

    binding_model = django_apps.get_model("contracts", "ContractFolderBinding")
    binding = binding_model.objects.filter(contract_id=contract_id).first()
    if binding is None or not binding.folder_path:
        return None

    storage_type = str(getattr(binding, "storage_type", "local") or "local")
    if storage_type == "local":
        candidates = _collect_local_contract_files(Path(binding.folder_path).expanduser())
        winner = _pick_latest_contract_file(candidates)
        return winner["path"].as_posix() if winner else None
    return _latest_contract_file_from_cloud(binding)


def _collect_local_contract_files(root: Path) -> list[dict[str, Any]]:
    """收集绑定文件夹中分类为合同正本的 pdf/docx 文件。"""
    if not root.is_dir():
        return []
    candidates: list[dict[str, Any]] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in _CONTRACT_PDF_SUFFIXES:
            continue
        if _is_contract_original(file_path.name, file_path.as_posix()):
            candidates.append(
                {
                    "path": file_path,
                    "mtime": file_path.stat().st_mtime,
                    "stem_key": _stem_group_key(file_path.stem),
                }
            )
    return candidates


def _latest_contract_file_from_cloud(binding: Any) -> str | None:  # pragma: no cover
    """云存储版本：walk 找合同文件，命中后下载为本地临时文件。"""
    from apps.cloud_storage.factory import create_provider_for_binding

    try:
        provider = create_provider_for_binding(binding)
        items = [
            {"name": f.name, "path": f.path, "mtime": f.modified_at or 0}
            for _dirpath, _subdirs, files in provider.walk(binding.folder_path)
            for f in files
            if not f.is_dir
            and Path(f.name).suffix.lower() in _CONTRACT_PDF_SUFFIXES
            and _is_contract_original(f.name, f.path)
        ]
    except Exception:
        logger.warning("立案附件云存储扫描失败（已忽略）", exc_info=True)
        return None

    winner = _pick_latest_contract_file(
        [
            {
                "path": Path(str(item["path"])),
                "mtime": item["mtime"],
                "stem_key": _stem_group_key(Path(str(item["path"])).stem),
            }
            for item in items
        ]
    )
    if winner is None:
        return None

    file_bytes = provider.read_file(str(winner["path"]))
    suffix = winner["path"].suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        logger.info("立案附件云存储文件已落地临时文件: %s", Path(tmp.name).name)
        return tmp.name


def _is_contract_original(filename: str, source_path: str) -> bool:
    """判断文件是否为合同正本（用于挑选上传 OA 的合同附件）。

    两级规则：
    1. 位于合同区文件夹段（如 "1-合同"）内 → 文件名含 合同/协议 即为正本
       （区域内默认排除监督卡/补充协议/发票等文书；案名含"合同纠纷"不算误报，
       因为位置已在合同区）；
    2. 区域外 → 文件名须命中强关键词（委托合同/服务合同/合同正本等）且不含
       案由描述（合同纠纷/协议争议等），宁缺勿滥——上传错文件到 OA 的代价
       远大于不传。
    """
    fn = str(filename or "").lower()
    if not fn:
        return False
    if any(kw in fn for kw in _ZONE_EXCLUDE_KEYWORDS):
        return False

    parent_parts = Path(str(source_path).replace("\\", "/")).parent.parts
    segments = [_NUMBER_PREFIX_RE.sub("", part) for part in parent_parts]
    in_contract_zone = any(segment.startswith(_ZONE_SEGMENT_PREFIX) for segment in segments if segment)
    if in_contract_zone:
        return "合同" in fn or "协议" in fn

    if any(fp in fn for fp in _FALSE_POSITIVE_PATTERNS):
        return False
    return any(kw in fn for kw in _STRONG_FILENAME_KEYWORDS)


def _pick_latest_contract_file(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """同名多版本取最新 mtime，跨名称 pdf 优先、再取最新 mtime。"""
    if not candidates:
        return None
    winners: dict[str, dict[str, Any]] = {}
    for item in candidates:
        current = winners.get(item["stem_key"])
        if current is None or item["mtime"] > current["mtime"]:
            winners[item["stem_key"]] = item
    ranked = sorted(
        winners.values(),
        key=lambda item: (item["path"].suffix.lower() == ".pdf", item["mtime"]),
        reverse=True,
    )
    return ranked[0]


def _stem_group_key(stem: str) -> str:
    """规范化 stem 作为同名多版本分组键。"""
    return re.sub(r"[\s._-]+", " ", str(stem or "").strip().lower()) or "_"


def stage_filing_attachment(contract_id: int, uploaded_file: Any) -> dict[str, Any]:  # pragma: no cover
    """拖拽的合同文件暂存为合同正本材料（content_hash 幂等去重）。"""
    from django.apps import apps as django_apps

    from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash_from_bytes
    from apps.contracts.services.contract.integrations.material_service import MaterialService

    material_model = django_apps.get_model("contracts", "FinalizedMaterial")

    file_bytes = uploaded_file.read()
    content_hash = compute_file_hash_from_bytes(file_bytes)
    if content_hash:
        existing = material_model.objects.filter(
            contract_id=contract_id, category="contract_original", content_hash=content_hash
        ).first()
        if existing is not None:
            logger.info("立案附件暂存命中已有材料: contract=%s material=%s", contract_id, existing.id)
            return _material_payload(existing, already_exists=True)

    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile(
        name=uploaded_file.name,
        content=file_bytes,
        content_type=getattr(uploaded_file, "content_type", "") or "application/octet-stream",
    )
    rel_path, original_name = MaterialService().save_material_file(upload, contract_id)

    material_kwargs: dict[str, Any] = {
        "contract_id": contract_id,
        "file_path": rel_path,
        "original_filename": original_name,
        "category": "contract_original",
    }
    if content_hash:
        material_kwargs["content_hash"] = content_hash
    material = material_model.objects.create(**material_kwargs)
    logger.info("立案附件暂存完成: contract=%s material=%s file=%s", contract_id, material.id, original_name)
    return _material_payload(material, already_exists=False)


def _material_payload(material: Any, *, already_exists: bool) -> dict[str, Any]:  # pragma: no cover
    return {
        "material_id": material.id,
        "filename": material.original_filename,
        "already_exists": already_exists,
    }
