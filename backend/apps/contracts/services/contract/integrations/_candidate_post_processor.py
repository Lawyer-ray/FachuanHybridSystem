"""候选文件后处理：归档匹配、docx 收集、已导入标记。"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from apps.contracts.models import FinalizedMaterial
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.contract.integrations.archive_classifier import classify_archive_material

from .file_hash_utils import compute_file_hash, compute_file_hash_from_bytes

logger = logging.getLogger(__name__)


def _normalize_docx_name(filename: str) -> str:
    """标准化文件名用于关键词匹配。"""
    return re.sub(r"\s+", "", str(filename or "").strip().lower())


# 身份类材料关键词：配合对方当事人名称识别"对方身份材料"。调解书/续封申请书等
# 文书名里也会出现对方当事人姓名，必须叠加身份关键词才排除，避免误杀裁判文书
_IDENTITY_MATERIAL_KEYWORDS: tuple[str, ...] = ("身份", "营业执照", "证照", "工商", "报告")


def authorization_family(filename: str) -> str:
    """识别授权委托类文书族；解除授权委托申请书是独立文书，不入授权委托书族。"""
    name = re.sub(r"\s+", "", str(filename or ""))
    if "法定代表人身份证明" in name:
        return "法定代表人身份证明"
    if "授权委托书" in name and "解除" not in name:
        return "授权委托书"
    if "所函" in name:
        return "所函"
    return ""


def _auth_recency(candidate: dict[str, Any]) -> tuple[str, bool]:
    """文书新近度排序键：修改时间（ISO 字符串可直接字典序比较），同刻 PDF 优先于 docx。"""
    modified = str(candidate.get("modified_at") or "")
    is_pdf = str(candidate.get("source_path") or "").lower().endswith(".pdf")
    return (modified, is_pdf)


class CandidatePostProcessor:
    """候选文件后处理器：归档清单匹配、docx 收集、已导入标记。"""

    def __init__(self, scan_service: Any) -> None:
        self._scan_service = scan_service

    def _relative_path_str(self, *, source_path: str, scan_root: Path) -> str:
        """计算文件父目录相对扫描根目录的路径，失败返回空字符串。"""
        try:
            file_path = Path(source_path).expanduser().resolve()
            parent_rel = file_path.parent.relative_to(scan_root)
            if str(parent_rel) == ".":
                return ""
            return parent_rel.as_posix()
        except (ValueError, RuntimeError):
            return ""

    def post_process_candidates(
        self,
        *,
        candidates: list[dict[str, Any]],
        archive_category: str,
        scan_folder: str,
        contract_id: int = 0,
        storage_provider: Any | None = None,
    ) -> list[dict[str, Any]]:
        """扫描后处理：归档清单项匹配 + docx 文件收集 + 跳过项过滤。"""
        processed: list[dict[str, Any]] = []
        if storage_provider is not None:
            scan_root_posix: PurePosixPath | None = PurePosixPath(scan_folder)
        else:
            scan_root_posix = None
            scan_root = Path(scan_folder).expanduser().resolve()

        for candidate in candidates:
            suggested_category = str(candidate.get("suggested_category") or "")

            # 所有非模板类别都需要经过跳过规则检查
            if suggested_category in ("archive_document", "authorization_material", "case_material", "invoice"):
                result = classify_archive_material(
                    filename=str(candidate.get("filename") or ""),
                    source_path=str(candidate.get("source_path") or ""),
                    archive_category=archive_category,
                )

                if result["category"] == "skip":
                    candidate["selected"] = False
                    candidate["skip_reason"] = result.get("reason", "跳过")
                    processed.append(candidate)
                    continue

                # invoice 类别不需要进一步的归档项匹配
                if suggested_category == "invoice":
                    processed.append(candidate)
                    continue

                if result["archive_item_code"]:
                    candidate["suggested_category"] = "case_material"
                    candidate["archive_item_code"] = result["archive_item_code"]
                    candidate["archive_item_name"] = result["archive_item_name"]
                    candidate["confidence"] = result["confidence"]
                    candidate["reason"] = result["reason"]
                else:
                    candidate["suggested_category"] = "case_material"
                    candidate["archive_item_code"] = ""
                    candidate["archive_item_name"] = "未匹配"
                    candidate["reason"] = result["reason"]
                    candidate["selected"] = False

            filename_lower = str(candidate.get("filename") or "").lower()
            if any(kw in filename_lower for kw in ("保单", "保函")):
                candidate["selected"] = False

            if candidate.get("suggested_category") == "case_material":
                if storage_provider is not None:
                    source = str(candidate.get("source_path") or "")
                    try:
                        assert scan_root_posix is not None
                        rel_path = str(PurePosixPath(source).relative_to(scan_root_posix))
                    except ValueError:
                        rel_path = source
                else:
                    rel_path = self._relative_path_str(
                        source_path=str(candidate.get("source_path") or ""),
                        scan_root=scan_root,
                    )
                if rel_path:
                    candidate["reason"] = rel_path

            processed.append(candidate)

        # 对方当事人身份材料不属于我方归档范围；授权委托类文书族只保留最新一份
        if contract_id:
            self._skip_opposing_identity_materials(processed, contract_id=contract_id)
        self._dedup_authorization_families(processed)

        if archive_category == "non_litigation":
            docx_candidates = self._collect_docx_files(scan_folder, archive_category, storage_provider=storage_provider)
            processed.extend(docx_candidates)

        if contract_id:
            self._mark_already_imported(processed, contract_id=contract_id, storage_provider=storage_provider)

        return processed

    def _skip_opposing_identity_materials(
        self,
        candidates: list[dict[str, Any]],
        *,
        contract_id: int,
    ) -> None:
        """跳过对方当事人的身份材料（身份证/身份信息/营业执照/企业报告等）。

        判定：文件名含对方当事人名称，且文件名或所在路径命中身份类关键词。
        所本命名惯例会把完整案件标题（含对方名称）嵌进几乎每个文件名，
        故先剥掉合同名称再匹配对方名称，避免误杀我方文书。
        """
        opposing_names, case_title = self._load_opposing_context(contract_id)
        if not opposing_names:
            return
        title_compact = re.sub(r"\s+", "", case_title)
        for candidate in candidates:
            if candidate.get("skip_reason"):
                continue
            filename = str(candidate.get("filename") or "")
            material_part = re.sub(r"\s+", "", filename).replace(title_compact, "") if title_compact else filename
            if not any(name in material_part for name in opposing_names):
                continue
            source_path = str(candidate.get("source_path") or "")
            identity_hint = any(kw in filename for kw in _IDENTITY_MATERIAL_KEYWORDS) or any(
                kw in source_path for kw in _IDENTITY_MATERIAL_KEYWORDS
            )
            if identity_hint:
                candidate["selected"] = False
                candidate["skip_reason"] = "对方当事人身份材料，无需归档"

    def _load_opposing_context(self, contract_id: int) -> tuple[list[str], str]:
        """合同对方当事人名称 + 合同名称（案件标题），加载失败按无对方处理。"""
        from apps.contracts.models import Contract, ContractParty

        try:
            contract = Contract.objects.filter(id=contract_id).only("name").first()
            case_title = str(getattr(contract, "name", "") or "")
            parties = ContractParty.objects.filter(contract_id=contract_id, role="OPPOSING").select_related("client")
            names = []
            for party in parties:
                client = getattr(party, "client", None)
                name = re.sub(r"\s+", "", str(getattr(client, "name", "") or "")) if client else ""
                if name:
                    names.append(name)
            return names, case_title
        except Exception:
            logger.warning("load_opposing_context_failed", extra={"contract_id": contract_id})
            return [], ""

    def _dedup_authorization_families(self, candidates: list[dict[str, Any]]) -> None:
        """授权委托书/法定代表人身份证明书/所函 同族只保留最新一份。

        同一文书常有 docx 草稿 + 签章 PDF、一审与执行各留一套旧版，
        归档只需最新一份；误放进来的他案同名旧文书也会被"最新者胜"淘汰。
        """
        families: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            if candidate.get("skip_reason"):
                continue
            family = authorization_family(str(candidate.get("filename") or ""))
            if family:
                families[family].append(candidate)

        for members in families.values():
            if len(members) < 2:
                continue
            latest = max(members, key=_auth_recency)
            for member in members:
                if member is not latest:
                    member["selected"] = False
                    member["skip_reason"] = "重复文书，已取最新一份"

    def _collect_docx_files(
        self,
        scan_folder: str,
        archive_category: str,
        storage_provider: Any | None = None,
    ) -> list[dict[str, Any]]:
        """单独收集 docx/doc 文件，仅非诉项目且仅含修订版/批注版关键词。"""
        if archive_category != "non_litigation":
            return []

        _DOCX_REVISION_KEYWORDS = ("修订版", "批注版", "律师修订")

        if storage_provider is not None:
            return self._collect_docx_files_cloud(scan_folder, storage_provider, _DOCX_REVISION_KEYWORDS)

        root = Path(scan_folder).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return []

        docx_files = [
            p
            for p in root.rglob("*")
            if p.is_file()
            and p.suffix.lower() in (".docx", ".doc")
            and any(kw in _normalize_docx_name(p.name) for kw in _DOCX_REVISION_KEYWORDS)
        ]
        docx_files.sort(key=lambda x: x.as_posix())

        deduped = self._scan_service._deduplicate_files(docx_files)

        candidates: list[dict[str, Any]] = []
        for item in deduped:
            file_path = item["path"]
            stat = file_path.stat()

            archive_item_code = ""
            archive_item_name = "未匹配"
            reason = "常法docx（修订版/批注版）→ 转 PDF"
            normalized_name = _normalize_docx_name(file_path.name)

            if "律师函" in normalized_name:
                archive_item_code = "nl_8"
                archive_item_name = "法律意见书、律师函等"
                reason = "常法docx（律师函）→ nl_8"
            else:
                archive_item_code = "nl_9"
                archive_item_name = "案件其它关联材料"
                reason = "常法docx（修订版/批注版）→ nl_9"

            candidates.append(
                {
                    "source_path": file_path.as_posix(),
                    "filename": file_path.name,
                    "file_size": int(stat.st_size),
                    "modified_at": "",
                    "base_name": item["base_name"],
                    "version_token": item["version_token"],
                    "extract_method": "none",
                    "text_excerpt": "",
                    "suggested_category": "case_material",
                    "confidence": 0.85,
                    "reason": reason,
                    "selected": True,
                    "is_docx": True,
                    "archive_item_code": archive_item_code,
                    "archive_item_name": archive_item_name,
                }
            )

        return candidates

    def _collect_docx_files_cloud(
        self,
        scan_folder: str,
        storage_provider: Any,
        revision_keywords: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        """云存储版本的 docx 文件收集。"""
        all_files: list[dict[str, Any]] = []
        for _dirpath, _subdirs, files in storage_provider.walk(scan_folder):
            for f in files:
                if not f.is_dir and PurePosixPath(f.name).suffix.lower() in (".docx", ".doc"):
                    if any(kw in _normalize_docx_name(f.name) for kw in revision_keywords):
                        all_files.append(
                            {
                                "name": f.name,
                                "path": f.path,
                                "size": f.size,
                                "modified_at": f.modified_at,
                            }
                        )

        if not all_files:
            return []

        all_files.sort(key=lambda x: x["path"])

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in all_files:
            stem = PurePosixPath(item["name"]).stem
            grouped[stem].append(item)

        deduped: list[dict[str, Any]] = []
        for group_items in grouped.values():
            group_items.sort(key=lambda x: (-x["modified_at"], x["path"]))
            deduped.append(group_items[0])

        candidates: list[dict[str, Any]] = []
        for item in deduped:
            archive_item_code = ""
            archive_item_name = "未匹配"
            reason = "常法docx（修订版/批注版）→ 转 PDF"
            normalized_name = _normalize_docx_name(item["name"])

            if "律师函" in normalized_name:
                archive_item_code = "nl_8"
                archive_item_name = "法律意见书、律师函等"
                reason = "常法docx（律师函）→ nl_8"
            else:
                archive_item_code = "nl_9"
                archive_item_name = "案件其它关联材料"
                reason = "常法docx（修订版/批注版）→ nl_9"

            candidates.append(
                {
                    "source_path": item["path"],
                    "filename": item["name"],
                    "file_size": item["size"],
                    "modified_at": "",
                    "base_name": normalized_name,
                    "version_token": "",
                    "extract_method": "none",
                    "text_excerpt": "",
                    "suggested_category": "case_material",
                    "confidence": 0.85,
                    "reason": reason,
                    "selected": True,
                    "is_docx": True,
                    "archive_item_code": archive_item_code,
                    "archive_item_name": archive_item_name,
                }
            )

        return candidates

    def _mark_already_imported(
        self,
        candidates: list[dict[str, Any]],
        *,
        contract_id: int,
        storage_provider: Any | None = None,
    ) -> None:
        """标记已导入文件：计算文件哈希，与已有材料比对。"""
        existing_hashes: set[str] = set(
            FinalizedMaterial.objects.filter(
                contract_id=contract_id,
                content_hash__gt="",
            ).values_list("content_hash", flat=True)
        )

        if not existing_hashes:
            for candidate in candidates:
                candidate["already_imported"] = False
            return

        for candidate in candidates:
            if candidate.get("skip_reason"):
                candidate["already_imported"] = False
                continue

            source_path = str(candidate.get("source_path") or "").strip()
            if not source_path:
                continue

            try:
                if storage_provider is not None:
                    file_bytes = storage_provider.read_file(source_path)
                    content_hash = compute_file_hash_from_bytes(file_bytes)
                else:
                    file_path = Path(source_path)
                    if not file_path.exists() or not file_path.is_file():
                        continue
                    content_hash = compute_file_hash(file_path)
            except Exception:
                logger.warning("mark_imported_hash_failed", extra={"source_path": source_path})
                continue

            if content_hash and content_hash in existing_hashes:
                candidate["already_imported"] = True
                candidate["selected"] = False
            else:
                candidate["already_imported"] = False
