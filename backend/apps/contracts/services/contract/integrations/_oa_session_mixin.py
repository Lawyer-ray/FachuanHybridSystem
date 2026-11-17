"""会话生命周期与状态（``ContractOASyncService`` 的 活动会话创建 / 任务提交 / 会话读取 / 状态载荷 / 陈旧判定 / 缺失合同查询）。

从 ``contract_oa_sync_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``contract_oa_sync_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``ContractOASyncSession`` / ``timezone`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``contract_oa_sync_service.Contract`` 等 7 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Q

from apps.core.dependencies.core import build_task_submission_service

from ._oa_service_contract import _OAServiceContract

if TYPE_CHECKING:
    from apps.contracts.models import Contract, ContractOASyncSession

logger = logging.getLogger(__name__)


class _OASessionMixin(_OAServiceContract):
    """子域 mixin：具体方法见 ``contract_oa_sync_service.ContractOASyncService``。"""

    def list_missing_oa_contracts(self) -> list[dict[str, Any]]:
        """列出缺少 OA 关键信息的合同。"""
        contracts = list(self._build_missing_contract_queryset())
        return self._serialize_missing_contracts(contracts)

    def create_or_get_active_session(self, *, started_by: Any | None) -> ContractOASyncSession:  # pragma: no cover
        """创建或复用进行中的会话。"""
        existing = (
            self._host.ContractOASyncSession.objects.filter(status__in=self._ACTIVE_STATUSES)
            .order_by("-created_at")
            .first()
        )
        if existing is not None:
            if self._is_stale_active_session(existing):
                logger.warning(
                    "contract_oa_sync_stale_session_detected",
                    extra={"session_id": existing.id, "status": existing.status},
                )
                self._update_session(
                    existing,
                    status=self._host.ContractOASyncStatus.FAILED,
                    progress_message="检测到陈旧会话，已重置",
                    error_message="上一次同步任务异常中断，请重新发起",
                    completed_at=self._host.timezone.now(),
                )
            else:
                return existing

        started_by_user = started_by if getattr(started_by, "is_authenticated", False) else None
        return self._host.ContractOASyncSession.objects.create(
            status=self._host.ContractOASyncStatus.PENDING,
            progress_message="等待启动",
            started_by=started_by_user,
        )

    def submit_session_task(self, *, session: ContractOASyncSession) -> ContractOASyncSession:  # pragma: no cover
        """提交会话异步任务。"""
        if session.status == self._host.ContractOASyncStatus.RUNNING and session.task_id:
            return session

        task_id = build_task_submission_service().submit(
            "apps.contracts.services.contract.integrations.contract_oa_sync_service.run_contract_oa_sync_task",
            args=[int(session.id)],
            task_name=f"contract_oa_sync_{session.id}",
            timeout=3600,  # 全量导入含分钟级 Playwright 流程，覆盖全局 600s 默认超时
        )
        self._host.ContractOASyncSession.objects.filter(id=session.id).update(
            status=self._host.ContractOASyncStatus.PENDING,
            task_id=str(task_id),
            progress_message="同步任务已入队，等待执行",
            error_message="",
            updated_at=self._host.timezone.now(),
        )
        session.refresh_from_db()
        return session

    def get_session(self, *, session_id: int) -> ContractOASyncSession | None:  # pragma: no cover
        return self._host.ContractOASyncSession.objects.filter(id=session_id).first()

    def build_status_payload(self, *, session: ContractOASyncSession) -> dict[str, Any]:
        payload = dict(session.result_payload or {})
        summary = payload.get("summary") or {}
        error_message = str(session.error_message or "")
        sso_login_url = str(payload.get("sso_login_url") or "").strip() or self._extract_sso_login_url(error_message)
        return {
            "session_id": int(session.id),
            "status": session.status,
            "progress_message": str(session.progress_message or ""),
            "total_count": int(session.total_count or 0),
            "processed_count": int(session.processed_count or 0),
            "matched_count": int(session.matched_count or 0),
            "multiple_count": int(session.multiple_count or 0),
            "not_found_count": int(session.not_found_count or 0),
            "error_count": int(session.error_count or 0),
            "error_message": error_message,
            "sso_login_url": sso_login_url,
            "summary": {
                "matched_count": int(summary.get("matched_count", 0) or 0),
                "multiple_count": int(summary.get("multiple_count", 0) or 0),
                "not_found_count": int(summary.get("not_found_count", 0) or 0),
                "error_count": int(summary.get("error_count", 0) or 0),
            },
            "items": payload.get("items", []),
            "remaining_contracts": payload.get("remaining_contracts", []),
            "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        }

    def _is_stale_active_session(self, session: ContractOASyncSession) -> bool:
        if session.status not in self._ACTIVE_STATUSES:
            return False

        updated_at = session.updated_at
        if updated_at is None:
            return True

        stale_before = self._host.timezone.now() - timedelta(minutes=self._STALE_RUNNING_MINUTES)
        return bool(updated_at < stale_before)

    def _build_missing_contract_queryset(self) -> Any:
        return (
            self._host.Contract.objects.filter(
                Q(law_firm_oa_url="")
                | Q(law_firm_oa_url="None")
                | Q(law_firm_oa_case_number__isnull=True)
                | Q(law_firm_oa_case_number="")
                | Q(law_firm_oa_case_number="None")
            )
            .only("id", "name", "law_firm_oa_url", "law_firm_oa_case_number")
            .order_by("id")
        )

    def _serialize_missing_contracts(self, contracts: list[Contract]) -> list[dict[str, Any]]:
        return [
            {
                "id": int(contract.id),
                "name": str(contract.name or ""),
                "law_firm_oa_url": str(contract.law_firm_oa_url or ""),
                "law_firm_oa_case_number": str(contract.law_firm_oa_case_number or ""),
            }
            for contract in contracts
        ]

    def _update_session(self, session: ContractOASyncSession, **fields: Any) -> None:  # pragma: no cover
        if not fields:
            return
        fields["updated_at"] = self._host.timezone.now()
        self._host.ContractOASyncSession.objects.filter(id=session.id).update(**fields)
        for key, value in fields.items():
            if key != "updated_at":
                setattr(session, key, value)


logger = logging.getLogger(__name__)
