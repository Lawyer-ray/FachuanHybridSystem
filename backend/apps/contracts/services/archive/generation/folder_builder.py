"""归档文件夹生成。"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial

from ..category_mapping import get_archive_category
from ..constants import ARCHIVE_CHECKLIST, ARCHIVE_FILE_NUMBERING, ARCHIVE_FOLDER_NAME
from .document_generator import generate_archive_documents, generate_single_archive_document
from .pdf_utils import add_page_numbers, compile_case_materials_pdf

logger = logging.getLogger("apps.contracts.archive")

# 归档分类 → 案卷目录清单编号映射（用于延迟重新生成）
_ARCHIVE_CATALOG_CODES: dict[str, str] = {
    "non_litigation": "nl_3",
    "litigation": "lt_3",
    "criminal": "cr_3",
}


def _cleanup_temp_files(temp_files: list[Path]) -> None:
    """清理临时 PDF 文件。"""
    for tmp in temp_files:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


def generate_archive_folder(contract: Contract) -> dict[str, Any]:  # pragma: no cover
    """生成归档文件夹到合同绑定的文件夹根目录。

    流程：
    1. 先调用 generate_archive_documents() 生成模板文书到 DB
    2. 在本地 staging 目录组装产物（1-3号 docx、4-案卷材料.pdf、5-Final案卷材料.pdf）
    3. 产物统一经 save_file_to_bound_folder() 写入绑定目录的「归档文件夹」子目录

    本地与云存储均在 staging 目录完成组装，最后统一发布，
    收敛"本地直写 + 云侧手写上传循环"双实现为单一入口。
    """
    import shutil
    import tempfile

    from apps.contracts.models.folder_binding import ContractFolderBinding

    try:
        binding = contract.folder_binding
    except ContractFolderBinding.DoesNotExist:
        binding = None

    if not binding or not binding.folder_path:
        return {"success": False, "error": "合同未绑定文件夹"}

    # 判断是否为云存储
    storage_type = getattr(binding, "storage_type", "local")
    is_cloud = storage_type != "local"

    if is_cloud:
        archive_dir_target = f"{binding.folder_path.rstrip('/')}/{ARCHIVE_FOLDER_NAME}"
    else:
        folder_path = Path(binding.folder_path)
        if not folder_path.exists():
            return {"success": False, "error": f"绑定文件夹不存在: {binding.folder_path}"}
        archive_dir_target = str(folder_path / ARCHIVE_FOLDER_NAME)

    # 统一在本地临时目录组装产物，发布时再由 save_file_to_bound_folder 落盘
    temp_dir = tempfile.mkdtemp(prefix="archive_")
    staging_dir = Path(temp_dir) / ARCHIVE_FOLDER_NAME
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        return _generate_archive_folder_inner(
            contract=contract,
            staging_dir=staging_dir,
            archive_dir_target=archive_dir_target,
            folder_path_display=binding.folder_path,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _generate_archive_folder_inner(
    contract: Contract,
    staging_dir: Path,
    archive_dir_target: str,
    folder_path_display: str,
) -> dict[str, Any]:  # pragma: no cover
    """归档文件夹生成的核心逻辑（本地和云存储共用）。

    产物先写入本地 staging 目录，最后统一发布到绑定目录。
    """

    # 生成模板文书到 DB
    doc_results = generate_archive_documents(contract)
    archive_category = get_archive_category(contract.case_type)
    catalog_code = _ARCHIVE_CATALOG_CODES.get(archive_category)
    if catalog_code:
        catalog_result = generate_single_archive_document(contract, catalog_code)
        for i, r in enumerate(doc_results):
            if r.get("template_subtype") == "inner_catalog":
                doc_results[i] = catalog_result
                break

    from django.utils import timezone

    contract_name = contract.name or "未命名合同"
    today_str = timezone.localdate().strftime("%Y%m%d")
    generated_docs: list[str] = []
    errors: list[str] = []

    # 写入1-3号模板文书（仅 docx）
    for seq_num, (template_subtype, doc_name) in ARCHIVE_FILE_NUMBERING.items():
        if template_subtype == "case_materials":
            continue

        base_name = f"{seq_num}-{doc_name}（{contract_name}）_{today_str}"
        try:
            _write_template_doc_to_folder(
                contract=contract,
                template_subtype=template_subtype,
                seq_num=seq_num,
                doc_name=doc_name,
                archive_dir=staging_dir,
            )
            generated_docs.append(base_name)
        except Exception as e:
            error_msg = f"{base_name}: {e}"
            errors.append(error_msg)
            logger.exception("写入归档文书失败: %s", error_msg)

    # 生成"4-案卷材料.pdf"
    case_materials_name = f"4-案卷材料（{contract_name}）_{today_str}"
    case_materials_pdf_exists = False
    try:
        mat_result = compile_case_materials_pdf(contract, staging_dir)
        if mat_result.get("written"):
            generated_docs.append(case_materials_name)
            case_materials_pdf_exists = True
        elif mat_result.get("skipped"):
            logger.info("无可合并的案卷材料，跳过%s.pdf", case_materials_name)
        else:
            errors.append(f"{case_materials_name}: {mat_result.get('error', '未知错误')}")
    except Exception as e:
        errors.append(f"{case_materials_name}: {e}")
        logger.exception("生成案卷材料PDF失败")

    # 生成"5-Final案卷材料.pdf"
    final_name = f"5-Final案卷材料（{contract_name}）_{today_str}"
    try:
        final_result = _compile_final_archive_pdf(
            contract=contract,
            archive_dir=staging_dir,
            case_materials_pdf_exists=case_materials_pdf_exists,
        )
        if final_result.get("written"):
            generated_docs.append(final_name)
        elif final_result.get("skipped"):
            logger.info("跳过%s.pdf: %s", final_name, final_result.get("reason", ""))
        else:
            errors.append(f"{final_name}: {final_result.get('error', '未知错误')}")
    except Exception as e:
        errors.append(f"{final_name}: {e}")
        logger.exception("生成Final案卷材料PDF失败")

    logger.info(
        "归档文件夹组装完成: %s, 成功 %d 项, 失败 %d 项",
        staging_dir,
        len(generated_docs),
        len(errors),
        extra={"contract_id": contract.id, "staging_dir": str(staging_dir)},
    )

    # 产物统一经 save_file_to_bound_folder 写入绑定目录（本地/云存储单一入口）
    errors.extend(_publish_archive_products(contract, staging_dir))

    return {
        "success": True,
        "archive_dir": archive_dir_target,
        "generated_docs": generated_docs,
        "errors": errors,
        "folder_path": folder_path_display,
        "doc_results": doc_results,
    }


def _publish_archive_products(contract: Contract, staging_dir: Path) -> list[str]:  # pragma: no cover
    """将 staging 目录中的归档产物写入合同绑定目录的「归档文件夹」子目录。

    统一经 FolderBindingService.save_file_to_bound_folder() 落盘：
    本地绑定走 filesystem_service，云存储绑定走 provider，避免双实现。
    """
    from apps.contracts.services.folder.folder_binding_service import ARCHIVE_SUBDIR_KEY, FolderBindingService

    binding_service = FolderBindingService()
    publish_errors: list[str] = []
    for product in sorted(staging_dir.iterdir()):
        if not product.is_file():
            continue
        try:
            saved_path = binding_service.save_file_to_bound_folder(
                owner_id=contract.id,
                file_content=product.read_bytes(),
                file_name=product.name,
                subdir_key=ARCHIVE_SUBDIR_KEY,
            )
            if saved_path is None:
                publish_errors.append(f"{product.name}: 合同未绑定文件夹")
        except Exception as e:
            publish_errors.append(f"{product.name}: {e}")
            logger.exception(
                "归档产物写入绑定目录失败: %s",
                product.name,
                extra={"contract_id": contract.id, "product": product.name},
            )
    return publish_errors


def _write_template_doc_to_folder(
    contract: Contract,
    template_subtype: str,
    seq_num: int,
    doc_name: str,
    archive_dir: Path,
) -> None:  # pragma: no cover
    """将单个模板文书写入归档组装目录（仅 docx，archive_dir 为本地 staging 目录）。"""
    from django.utils import timezone

    from apps.core.services.storage_service import to_media_abs

    archive_category = get_archive_category(contract.case_type)
    checklist_items = ARCHIVE_CHECKLIST.get(archive_category, [])

    item_code = None
    for item in checklist_items:
        if item.get("template") == template_subtype:
            item_code = item["code"]
            break

    if not item_code:
        raise ValueError(f"未找到模板子类型 {template_subtype} 对应的清单项")

    material = FinalizedMaterial.objects.filter(
        contract=contract,
        archive_item_code=item_code,
    ).first()

    if not material:
        raise ValueError(f"模板文书尚未生成: {template_subtype}")

    if not material.file_path:
        raise ValueError(f"模板文书文件路径缺失: {template_subtype}")

    docx_path = to_media_abs(material.file_path)

    if not docx_path.exists():
        raise ValueError(f"docx文件不存在: {docx_path}")

    contract_name = contract.name or "未命名合同"
    today_str = timezone.localdate().strftime("%Y%m%d")
    base_name = f"{seq_num}-{doc_name}（{contract_name}）_{today_str}"

    dest_docx = archive_dir / f"{base_name}.docx"
    dest_docx.write_bytes(docx_path.read_bytes())


def _compile_final_archive_pdf(
    contract: Contract,
    archive_dir: Path,
    case_materials_pdf_exists: bool,
) -> dict[str, Any]:  # pragma: no cover
    """将1-3号模板文书的docx转PDF，与4-案卷材料PDF按序号合并，生成"5-Final案卷材料.pdf"。"""
    import pymupdf as fitz
    from django.utils import timezone

    from apps.documents.services.infrastructure.pdf_merge_utils import resolve_material_to_temp_pdf

    contract_name = contract.name or "未命名合同"
    today_str = timezone.localdate().strftime("%Y%m%d")

    pdf_files_to_merge: list[Path] = []
    temp_pdf_files: list[Path] = []

    for seq_num in sorted(ARCHIVE_FILE_NUMBERING.keys()):
        template_subtype, doc_name = ARCHIVE_FILE_NUMBERING[seq_num]

        if template_subtype == "case_materials":
            pdf_path = archive_dir / f"{seq_num}-{doc_name}（{contract_name}）_{today_str}.pdf"
            if not case_materials_pdf_exists or not pdf_path.exists():
                logger.info("4-案卷材料PDF不存在，跳过Final合并")
                _cleanup_temp_files(temp_pdf_files)
                return {
                    "written": False,
                    "skipped": True,
                    "page_count": 0,
                    "error": None,
                    "reason": "4-案卷材料PDF未生成",
                }
            pdf_files_to_merge.append(pdf_path)
            continue

        docx_path = archive_dir / f"{seq_num}-{doc_name}（{contract_name}）_{today_str}.docx"
        if not docx_path.exists():
            logger.warning("模板文书docx不存在，跳过: %s", docx_path.name)
            continue

        pdf_path, is_temp = resolve_material_to_temp_pdf(docx_path)
        if pdf_path is not None:
            pdf_files_to_merge.append(pdf_path)
            if is_temp:
                temp_pdf_files.append(pdf_path)
        else:
            logger.warning("docx转PDF失败: %s", docx_path.name)

    if not pdf_files_to_merge:
        _cleanup_temp_files(temp_pdf_files)
        return {"written": False, "skipped": True, "page_count": 0, "error": None, "reason": "无可合并的PDF文件"}

    merged_doc = fitz.open()
    try:
        for pdf_path in pdf_files_to_merge:
            try:
                src_doc = fitz.open(str(pdf_path))
                merged_doc.insert_pdf(src_doc)
                src_doc.close()
            except (OSError, ValueError) as e:
                logger.warning("合并PDF失败: %s, error: %s", pdf_path.name, e)

        if len(merged_doc) == 0:
            return {"written": False, "skipped": True, "page_count": 0, "error": "合并后PDF为空"}

        dest_pdf = archive_dir / f"5-Final案卷材料（{contract_name}）_{today_str}.pdf"
        merged_doc.save(str(dest_pdf))
        page_count = len(merged_doc)

        logger.info(
            "Final案卷材料PDF生成完成: %d 页, %d 份PDF合并",
            page_count,
            len(pdf_files_to_merge),
            extra={"contract_id": contract.id, "dest": str(dest_pdf)},
        )

        return {"written": True, "page_count": page_count, "skipped": False, "error": None}

    except Exception as e:
        logger.exception("合并Final案卷材料PDF失败")
        return {"written": False, "skipped": False, "page_count": 0, "error": str(e)}
    finally:
        merged_doc.close()
        for tmp in temp_pdf_files:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
                logger.info("已清理中间PDF: %s", tmp.name)


def resolve_latest_final_archive_file(contract: Contract) -> Path | None:
    """定位归档文件夹中最新的 "5-Final案卷材料*.pdf"，返回可读取的本地路径。

    本地存储直接返回归档目录内最新文件；云存储先下载到临时文件返回。
    未找到时返回 None，调用方应保持不加材料。归档材料即最终需提交到律所 OA 的
    "5-Final案卷材料"，打开 OA 的最后一步据此自动上传。
    """
    import os
    import tempfile

    from apps.contracts.models.folder_binding import ContractFolderBinding

    try:
        binding = contract.folder_binding
    except ContractFolderBinding.DoesNotExist:
        return None

    if not binding or not binding.folder_path:
        return None

    storage_type = getattr(binding, "storage_type", "local")
    if storage_type == "local":
        archive_dir = Path(binding.folder_path) / ARCHIVE_FOLDER_NAME
        if not archive_dir.is_dir():
            return None
        finals = sorted(
            (p for p in archive_dir.glob("5-Final案卷材料*.pdf")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return finals[0] if finals else None

    from apps.cloud_storage.factory import create_provider_for_binding

    provider = create_provider_for_binding(binding)
    archive_path = f"{binding.folder_path.rstrip('/')}/{ARCHIVE_FOLDER_NAME}"
    try:
        items = provider.list_directory(archive_path)
    except Exception:
        logger.warning(
            "resolve_final_archive_cloud_list_failed",
            extra={"contract_id": contract.id, "path": archive_path},
        )
        return None

    finals = [
        it for it in items if not it.is_dir and it.name.startswith("5-Final案卷材料") and it.name.endswith(".pdf")
    ]
    if not finals:
        return None

    best = max(finals, key=lambda it: it.modified_at or 0)
    try:
        content = provider.read_file(best.path)
    except Exception:
        logger.warning(
            "resolve_final_archive_cloud_read_failed",
            extra={"contract_id": contract.id, "path": best.path},
        )
        return None

    fd, tmp_path = tempfile.mkstemp(prefix="fc_final_archive_", suffix=".pdf")
    os.close(fd)
    Path(tmp_path).write_bytes(content)
    logger.info(
        "云存储归档Final案卷材料已下载到临时路径: %s",
        tmp_path,
        extra={"contract_id": contract.id, "cloud_path": best.path},
    )
    return Path(tmp_path)
