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


def generate_archive_folder(contract: Contract) -> dict[str, Any]:
    """生成归档文件夹到合同绑定的文件夹根目录。

    流程：
    1. 先调用 generate_archive_documents() 生成模板文书到 DB
    2. 在合同绑定文件夹下创建"归档文件夹"目录
    3. 将1-3号模板文书写入（仅 docx）
    4. 将剩余材料项合并为"4-案卷材料.pdf"（带页码）
    5. 将1-3号docx转PDF，与4号合并为"5-Final案卷材料.pdf"（无页码）
    """
    from apps.contracts.models.folder_binding import ContractFolderBinding

    try:
        binding = contract.folder_binding
    except ContractFolderBinding.DoesNotExist:
        binding = None

    if not binding or not binding.folder_path:
        return {"success": False, "error": "合同未绑定文件夹"}

    folder_path = Path(binding.folder_path)
    if not folder_path.exists():
        return {"success": False, "error": f"绑定文件夹不存在: {binding.folder_path}"}

    # 生成模板文书到 DB
    doc_results = generate_archive_documents(contract)

    # 重新生成案卷目录以确保内容完整
    archive_category = get_archive_category(contract.case_type)
    catalog_code = _ARCHIVE_CATALOG_CODES.get(archive_category)
    if catalog_code:
        catalog_result = generate_single_archive_document(contract, catalog_code)
        for i, r in enumerate(doc_results):
            if r.get("template_subtype") == "inner_catalog":
                doc_results[i] = catalog_result
                break

    # 创建归档文件夹
    archive_dir = folder_path / ARCHIVE_FOLDER_NAME
    archive_dir.mkdir(parents=True, exist_ok=True)

    from datetime import date

    contract_name = contract.name or "未命名合同"
    today_str = date.today().strftime("%Y%m%d")
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
                archive_dir=archive_dir,
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
        mat_result = compile_case_materials_pdf(contract, archive_dir)
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
            archive_dir=archive_dir,
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
        "归档文件夹生成完成: %s, 成功 %d 项, 失败 %d 项",
        archive_dir,
        len(generated_docs),
        len(errors),
        extra={"contract_id": contract.id, "archive_dir": str(archive_dir)},
    )

    return {
        "success": True,
        "archive_dir": str(archive_dir),
        "generated_docs": generated_docs,
        "errors": errors,
        "folder_path": str(folder_path),
        "doc_results": doc_results,
    }


def _write_template_doc_to_folder(
    contract: Contract,
    template_subtype: str,
    seq_num: int,
    doc_name: str,
    archive_dir: Path,
) -> None:
    """将单个模板文书写入归档文件夹（仅 docx）。"""
    from datetime import date

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

    docx_path = Path(material.file_path)
    if not docx_path.is_absolute():
        from django.conf import settings as django_settings
        docx_path = Path(django_settings.MEDIA_ROOT) / docx_path

    if not docx_path.exists():
        raise ValueError(f"docx文件不存在: {docx_path}")

    contract_name = contract.name or "未命名合同"
    today_str = date.today().strftime("%Y%m%d")
    base_name = f"{seq_num}-{doc_name}（{contract_name}）_{today_str}"

    dest_docx = archive_dir / f"{base_name}.docx"
    dest_docx.write_bytes(docx_path.read_bytes())


def _compile_final_archive_pdf(
    contract: Contract,
    archive_dir: Path,
    case_materials_pdf_exists: bool,
) -> dict[str, Any]:
    """将1-3号模板文书的docx转PDF，与4-案卷材料PDF按序号合并，生成"5-Final案卷材料.pdf"。"""
    import fitz

    from datetime import date

    from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

    contract_name = contract.name or "未命名合同"
    today_str = date.today().strftime("%Y%m%d")

    pdf_files_to_merge: list[Path] = []
    temp_pdf_files: list[Path] = []

    for seq_num in sorted(ARCHIVE_FILE_NUMBERING.keys()):
        template_subtype, doc_name = ARCHIVE_FILE_NUMBERING[seq_num]

        if template_subtype == "case_materials":
            pdf_path = archive_dir / f"{seq_num}-{doc_name}（{contract_name}）_{today_str}.pdf"
            if not case_materials_pdf_exists or not pdf_path.exists():
                logger.info("4-案卷材料PDF不存在，跳过Final合并")
                for tmp in temp_pdf_files:
                    with contextlib.suppress(OSError):
                        tmp.unlink(missing_ok=True)
                return {"written": False, "skipped": True, "page_count": 0, "error": None, "reason": "4-案卷材料PDF未生成"}
            pdf_files_to_merge.append(pdf_path)
            continue

        docx_path = archive_dir / f"{seq_num}-{doc_name}（{contract_name}）_{today_str}.docx"
        if not docx_path.exists():
            logger.warning("模板文书docx不存在，跳过: %s", docx_path.name)
            continue

        try:
            pdf_result = convert_docx_to_pdf(str(docx_path))
            if pdf_result and Path(pdf_result).exists():
                pdf_path = Path(pdf_result)
                pdf_files_to_merge.append(pdf_path)
                temp_pdf_files.append(pdf_path)
            else:
                logger.warning("docx转PDF失败: %s", docx_path.name)
        except Exception as e:
            logger.warning("docx转PDF异常: %s, error: %s", docx_path.name, e)

    if not pdf_files_to_merge:
        for tmp in temp_pdf_files:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
        return {"written": False, "skipped": True, "page_count": 0, "error": None, "reason": "无可合并的PDF文件"}

    merged_doc = fitz.open()
    try:
        for pdf_path in pdf_files_to_merge:
            try:
                src_doc = fitz.open(str(pdf_path))
                merged_doc.insert_pdf(src_doc)
                src_doc.close()
            except Exception as e:
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
