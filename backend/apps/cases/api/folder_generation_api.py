"""案件文件夹生成 API"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import Router

from apps.core.security import get_request_access_context

logger = logging.getLogger("apps.cases.api")
router = Router()


def _build_zip_from_structure(structure: dict[str, Any], parent: str = "") -> bytes:
    """递归将文件夹结构打包为 ZIP（只含空目录）"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _add_folders_to_zip(zf, structure, parent)
    return buf.getvalue()


def _add_folders_to_zip(zf: zipfile.ZipFile, node: dict[str, Any], parent: str) -> None:
    name = node.get("name", "")
    current = f"{parent}/{name}" if parent else name
    zf.writestr(f"{current}/", "")
    for child in node.get("children", []):
        _add_folders_to_zip(zf, child, current)


def _create_folders_on_disk(node: dict[str, Any], parent: Path) -> Path:
    """递归在磁盘上创建文件夹结构，返回根目录路径"""
    name = node.get("name", "")
    current = parent / name
    current.mkdir(parents=True, exist_ok=True)
    for child in node.get("children", []):
        _create_folders_on_disk(child, current)
    return current


@router.post("/{case_id}/generate-folder")
def generate_case_folder(request: HttpRequest, case_id: int) -> Any:
    """
    生成案件文件夹。
    - 若合同绑定了文件夹：在绑定路径下创建案件文件夹，返回 JSON
    - 否则：返回 ZIP 下载
    """
    from apps.cases.models import Case
    from apps.documents.models import FolderTemplate
    from apps.documents.services.generation.folder_generation_service import FolderGenerationService

    ctx = get_request_access_context(request)

    try:
        case = Case.objects.select_related("contract__folder_binding", "folder_binding").get(pk=case_id)
    except Case.DoesNotExist:
        return HttpResponse(status=404)

    # 匹配文件夹模板（case 类型）
    templates = FolderTemplate.objects.filter(
        template_type="case",
        is_active=True,
    )
    matched: FolderTemplate | None = None
    for t in templates:
        case_types: list[str] = t.case_types or []
        if case.case_type in case_types or "all" in case_types:
            matched = t
            break

    if not matched:
        return {"success": False, "message": "无匹配的文件夹模板"}

    # 生成文件夹名称：日期-案件名
    from datetime import date

    from apps.core.enums import CaseType

    today = date.today().strftime("%Y.%m.%d")
    case_type_display = dict(CaseType.choices).get(case.case_type, case.case_type or "")
    root_name = f"{today}-[{case_type_display}]{case.name}"

    svc = FolderGenerationService()
    structure = svc.generate_folder_structure(matched, root_name)

    # 判断是否有合同绑定文件夹
    contract_folder_path: str | None = None
    if case.contract and hasattr(case.contract, "folder_binding") and case.contract.folder_binding:
        contract_folder_path = case.contract.folder_binding.folder_path

    if contract_folder_path:
        parent = Path(contract_folder_path)
        if not parent.exists():
            return {"success": False, "message": f"合同绑定文件夹不存在: {contract_folder_path}"}
        created = _create_folders_on_disk(structure, parent)
        logger.info("案件文件夹已创建", extra={"case_id": case_id, "path": str(created)})
        return {"success": True, "message": f"案件文件夹已创建: {created}", "folder_path": str(created)}

    # 无绑定 → 下载 ZIP
    zip_bytes = _build_zip_from_structure(structure)
    response = HttpResponse(zip_bytes, content_type="application/zip")
    filename = f"{root_name}.zip"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
