"""会话查询与状态装配（``ContractFolderScanService`` 的 会话读取 / 清空 / 状态载荷装配）。

从 ``folder_scan_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``folder_scan_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``Path`` / ``ContractFolderScanSession`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``folder_scan_service.Contract`` 等 53 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from apps.contracts.models import ContractFolderScanSession

from apps.core.exceptions import NotFoundError, ValidationException

from ._scan_service_contract import _ScanServiceContract

logger = logging.getLogger(__name__)


class _SessionQueryMixin(_ScanServiceContract):
    """子域 mixin：具体方法见 ``folder_scan_service.ContractFolderScanService``。"""

    def get_session(self, *, contract_id: int, session_id: UUID) -> ContractFolderScanSession:
        try:
            return self._host.ContractFolderScanSession.objects.get(id=session_id, contract_id=contract_id)
        except self._host.ContractFolderScanSession.DoesNotExist:
            raise NotFoundError("扫描会话不存在") from None

    def get_latest_session(self, *, contract_id: int) -> ContractFolderScanSession | None:  # pragma: no cover
        """返回合同最新的扫描会话，没有则返回 None。"""
        return (
            self._host.ContractFolderScanSession.objects.filter(contract_id=contract_id).order_by("-created_at").first()
        )

    def clear_scan_sessions(self, *, contract_id: int) -> int:  # pragma: no cover
        """清空合同的扫描会话（弹窗「清空结果」）。

        只删扫描工作区（候选/建议/提取结果），不动已导入的材料与回填的案号。
        扫描进行中拒绝清空，避免任务回写已删除的会话行。
        """
        self._ensure_contract_exists(contract_id)
        has_active = self._host.ContractFolderScanSession.objects.filter(
            contract_id=contract_id,
            status__in=self._ACTIVE_STATUSES,
        ).exists()
        if has_active:
            raise ValidationException(message="扫描进行中，请等待完成后再清空")
        deleted, _rows = self._host.ContractFolderScanSession.objects.filter(contract_id=contract_id).delete()
        logger.info("contract_folder_scan_cleared", extra={"contract_id": contract_id, "deleted": deleted})
        return deleted

    def build_status_payload(self, *, session: ContractFolderScanSession) -> dict[str, Any]:
        payload = dict(session.result_payload or {})
        summary = payload.get("summary") or {}
        candidates = payload.get("candidates") or []

        return {
            "session_id": str(session.id),
            "status": session.status,
            "progress": int(session.progress or 0),
            "current_file": session.current_file or "",
            "summary": {
                "total_files": int(summary.get("total_files", 0) or 0),
                "deduped_files": int(summary.get("deduped_files", 0) or 0),
                "classified_files": int(summary.get("classified_files", 0) or 0),
                # 闸 2：被判定为作废票（文件名含「红字开具」）因而未勾选的候选数
                "skipped_voided": int(summary.get("skipped_voided", 0) or 0),
            },
            "candidates": candidates,
            "error_message": session.error_message or "",
            "archive_category": payload.get("archive_category") or "",
            "archive_item_options": payload.get("archive_item_options") or [],
            "work_log_suggestions": payload.get("work_log_suggestions") or [],
            "ai_classify_result": payload.get("ai_classify_result") or {},
            "case_info_extractions": payload.get("case_info_extractions") or [],
        }
