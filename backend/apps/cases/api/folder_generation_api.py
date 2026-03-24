"""案件文件夹生成 API"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import Router

from apps.documents.api.download_response_factory import build_download_response

logger = logging.getLogger("apps.cases.api")
router = Router()


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

    try:
        case = Case.objects.select_related("contract__folder_binding", "folder_binding").prefetch_related(
            "parties__client"
        ).get(pk=case_id)
    except Case.DoesNotExist:
        return HttpResponse(status=404)

    # 获取我方当事人的诉讼地位
    our_legal_statuses = [
        party.legal_status
        for party in case.parties.all()
        if getattr(party.client, "is_our_client", False) and party.legal_status
    ]

    # 使用 TemplateMatchingService 进行匹配（与前端一致）
    from apps.documents.services.template.template_matching_service import TemplateMatchingService

    template_service = TemplateMatchingService()
    matched_candidates = template_service.find_matching_case_folder_templates_list(
        case_type=case.case_type,
        legal_statuses=our_legal_statuses,
    )

    if not matched_candidates:
        return {"success": False, "message": "无匹配的文件夹模板"}

    # 取第一个匹配的模板（已按优先级排序）
    matched_template_id = matched_candidates[0]["id"]
    matched = FolderTemplate.objects.get(pk=matched_template_id)

    # 生成文件夹名称：日期-案件名
    from datetime import date

    from apps.core.enums import CaseType

    today = date.today().strftime("%Y.%m.%d")
    case_type_display = dict(CaseType.choices).get(case.case_type, case.case_type or "")
    root_name = f"{today}-[{case_type_display}]{case.name}"

    svc = FolderGenerationService()

    # 判断是否有合同绑定文件夹
    contract_folder_path: str | None = None
    if case.contract and hasattr(case.contract, "folder_binding") and case.contract.folder_binding:
        contract_folder_path = case.contract.folder_binding.folder_path

    zip_bytes = svc.generate_case_folder_with_documents(case, matched, root_name)
    filename = f"{root_name}.zip"

    if contract_folder_path:
        parent = Path(contract_folder_path)
        if not parent.exists():
            return {"success": False, "message": f"合同绑定文件夹不存在: {contract_folder_path}"}
        try:
            with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
                zf.extractall(str(parent))
        except (OSError, zipfile.BadZipFile) as e:
            logger.error("ZIP 解压失败: %s", e, extra={"case_id": case_id})
            return {"success": False, "message": f"ZIP 解压失败: {e}"}
        logger.info("案件文件夹已解压到合同文件夹", extra={"case_id": case_id, "path": str(parent)})
        return {"success": True, "message": f"文件已保存到: {parent}", "folder_path": str(parent)}

    # 无绑定 → 下载 ZIP
    return build_download_response(content=zip_bytes, filename=filename, content_type="application/zip")
