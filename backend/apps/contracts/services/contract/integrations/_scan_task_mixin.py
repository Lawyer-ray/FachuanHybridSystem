"""扫描启动与任务执行（``ContractFolderScanService`` 的 扫描调度 / 子文件夹列举 / Django-Q 任务执行）。

从 ``folder_scan_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``folder_scan_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``Path`` / ``ContractFolderScanSession`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``folder_scan_service.Contract`` 等 53 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from apps.contracts.models import ContractFolderScanSession

from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException

from ._scan_service_contract import _ScanServiceContract

logger = logging.getLogger(__name__)


class _ScanTaskMixin(_ScanServiceContract):
    """子域 mixin：具体方法见 ``folder_scan_service.ContractFolderScanService``。"""

    def start_scan(
        self,
        *,
        contract_id: int,
        started_by: Any | None,
        rescan: bool = False,
        scan_subfolder: str = "",
    ) -> ContractFolderScanSession:  # pragma: no cover
        self._ensure_contract_exists(contract_id)
        binding = self._get_accessible_binding(contract_id)
        storage_provider = self._make_provider_for_binding(binding)
        scan_scope = self._resolve_scan_scope(binding.folder_path, scan_subfolder, storage_provider=storage_provider)

        if not rescan:
            existing = (
                self._host.ContractFolderScanSession.objects.filter(
                    contract_id=contract_id, status__in=self._ACTIVE_STATUSES
                )
                .order_by("-created_at")
                .first()
            )
            if existing:
                existing_subfolder = self._extract_scan_subfolder(existing.result_payload)
                if existing_subfolder == scan_scope["scan_subfolder"]:
                    return existing
                raise ValidationException(
                    message="已有进行中的扫描任务，请等待完成或使用“重新扫描”",
                    errors={"session_id": str(existing.id)},
                )

            # 复用同子文件夹的已完成会话，避免重复扫描
            completed_match = (
                self._host.ContractFolderScanSession.objects.filter(
                    contract_id=contract_id,
                    status=self._host.ContractFolderScanStatus.COMPLETED,
                )
                .order_by("-created_at")
                .first()
            )
            if completed_match:
                completed_subfolder = self._extract_scan_subfolder(completed_match.result_payload)
                if completed_subfolder == scan_scope["scan_subfolder"]:
                    return completed_match

        session = self._host.ContractFolderScanSession.objects.create(
            contract_id=contract_id,
            status=self._host.ContractFolderScanStatus.PENDING,
            progress=0,
            current_file="",
            result_payload={
                "summary": {},
                "candidates": [],
                "scan_scope": scan_scope,
            },
            started_by=started_by if getattr(started_by, "is_authenticated", False) else None,
        )

        task_id = self._host.build_task_submission_service().submit(
            "apps.contracts.services.contract.integrations.folder_scan_service.run_contract_folder_scan_task",
            args=[str(session.id)],
            task_name=f"contract_folder_scan_{session.id}",
        )

        self._host.ContractFolderScanSession.objects.filter(id=session.id).update(
            status=self._host.ContractFolderScanStatus.RUNNING,
            task_id=str(task_id),
            updated_at=timezone.now(),
        )
        session.refresh_from_db()
        logger.info(
            "contract_folder_scan_submitted",
            extra={
                "contract_id": contract_id,
                "session_id": str(session.id),
                "scan_subfolder": scan_scope["scan_subfolder"],
            },
        )
        return session

    def list_scan_subfolders(self, *, contract_id: int) -> dict[str, Any]:  # pragma: no cover
        self._ensure_contract_exists(contract_id)
        binding = self._get_accessible_binding(contract_id)

        # Cloud storage: use provider to list subdirectories
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type != "local":
            provider = self._make_provider_for_binding(binding)
            root_path = binding.folder_path
            try:
                children = provider.list_directory(root_path) if provider else []
            except Exception:
                children = []
            subfolders = []
            for child in children:
                if not child.is_dir:
                    continue
                if child.name.startswith("."):
                    continue
                subfolders.append({"relative_path": child.name, "display_name": child.name})
            subfolders.sort(key=lambda x: x["display_name"].lower())
            return {"root_path": root_path, "subfolders": subfolders}

        # Local filesystem
        root = self._host.Path(binding.folder_path).expanduser().resolve()

        subfolders_local: list[dict[str, str]] = []
        for child_local in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child_local.name.startswith("."):
                continue
            if not child_local.is_dir():
                continue
            resolved_child = child_local.resolve()
            if not self._is_within_root(root, resolved_child):
                continue
            subfolders_local.append(
                {
                    "relative_path": child_local.name,
                    "display_name": child_local.name,
                }
            )

        return {
            "root_path": root.as_posix(),
            "subfolders": subfolders_local,
        }

    def run_scan_task(self, *, session_id: str) -> None:  # pragma: no cover
        session = self._host.ContractFolderScanSession.objects.select_related("contract").filter(id=session_id).first()
        if not session:
            logger.warning("contract_folder_scan_session_missing", extra={"session_id": session_id})
            return

        try:
            binding = self._get_accessible_binding(session.contract_id)
            storage_provider = self._make_provider_for_binding(binding)
            payload = dict(session.result_payload or {})
            scan_scope = self._resolve_scan_scope(
                binding.folder_path,
                self._extract_scan_subfolder(payload),
                storage_provider=storage_provider,
            )

            def _progress(status: str, progress: int, current_file: str | None) -> None:  # pragma: no cover
                # 文件遍历结束（"completed"）后还有后处理/工作日志/案件信息提取阶段，
                # 此时不能提前置 COMPLETED——轮询端见 COMPLETED 即停止轮询，会拿到
                # 空结果误报「未找到可导入的文件」；COMPLETED 只由最终原子落库写入
                mapped_status = self._host.ContractFolderScanStatus.RUNNING
                shown_progress = int(progress)
                if status == "classifying":
                    mapped_status = self._host.ContractFolderScanStatus.CLASSIFYING
                elif status == "completed":
                    shown_progress = min(shown_progress, 99)

                self._host.ContractFolderScanSession.objects.filter(id=session.id).update(
                    status=mapped_status,
                    progress=shown_progress,
                    current_file=current_file or "",
                    updated_at=timezone.now(),
                )

            result = self._scan_service.scan_folder(
                folder_path=scan_scope["scan_folder"],
                domain="contract",
                progress_callback=_progress,
                storage_provider=storage_provider,
                exclude_dir_keywords=self._exclude_dir_keywords(scan_subfolder=scan_scope["scan_subfolder"]),
            )
            result["scan_scope"] = scan_scope

            contract = session.contract
            archive_category = self._host.get_archive_category(getattr(contract, "case_type", ""))

            candidates = result.get("candidates") or []
            skipped_voided = self._mark_voided_candidates(candidates)
            if skipped_voided:
                logger.info(
                    "folder_scan_skip_voided_dir",
                    extra={"contract_id": session.contract_id, "skipped_voided": skipped_voided},
                )
            result["skipped_voided"] = skipped_voided
            candidates = self._post_processor.post_process_candidates(
                candidates=candidates,
                archive_category=archive_category,
                scan_folder=scan_scope["scan_folder"],
                contract_id=session.contract_id,
                storage_provider=storage_provider,
            )
            result["candidates"] = candidates

            # 工作日志建议
            work_log_suggestions = self._host.collect_work_log_suggestions(
                scan_scope["scan_folder"], archive_category, storage_provider=storage_provider
            )
            result["work_log_suggestions"] = work_log_suggestions

            # 裁判文书案件信息提取（审级/法院名称/案号/主文），单文件失败不阻断扫描
            try:
                result["case_info_extractions"] = self._host.extract_case_info_from_candidates(
                    candidates, storage_provider=storage_provider
                )
            except Exception:
                logger.exception("case_info_extraction_error", extra={"session_id": session_id})
                result["case_info_extractions"] = []

            # 归档清单项选项
            archive_item_options = self._host.collect_archive_item_options(archive_category)
            result["archive_item_options"] = archive_item_options
            result["archive_category"] = archive_category

            self._host.ContractFolderScanSession.objects.filter(id=session.id).update(
                status=self._host.ContractFolderScanStatus.COMPLETED,
                progress=100,
                current_file="",
                result_payload=result,
                error_message="",
                updated_at=timezone.now(),
            )
        except Exception as exc:
            from apps.cloud_storage.exceptions import CloudStorageError

            if isinstance(exc, CloudStorageError):
                error_msg = str(exc)
            else:
                error_msg = f"扫描失败: {type(exc).__name__}"
            logger.exception("contract_folder_scan_failed", extra={"session_id": session_id})
            self._host.ContractFolderScanSession.objects.filter(id=session.id).update(
                status=self._host.ContractFolderScanStatus.FAILED,
                error_message=error_msg,
                updated_at=timezone.now(),
            )

    # ── Private helpers ─────────────────────────────────────────────────
