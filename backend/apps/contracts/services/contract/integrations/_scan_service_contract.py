"""``ContractFolderScanService`` 拆 mixin 后的**静态类型契约**。

这个模块只服务 mypy，**不参与运行期**（所有名字都在 ``TYPE_CHECKING`` 下）。

背景
----
``folder_scan_service.py`` 按子域拆成 5 个同目录 mixin。拆分有一个硬约束：
测试有 53 处 ``patch("...folder_scan_service.Contract")`` 这类**按绑定位置**打桩的写法，
一旦把方法体搬到别处、模型名也随之搬到别处，patch 就全部失效（需同步改 6 个测试文件）。

所以采用「方法体搬走，但业务名统一经 ``self._host`` 回查宿主模块 globals」的做法：

- 运行期：``_host`` 是宿主类上的 ``@property``，返回 ``sys.modules[__name__]``；
- 静态期：本模块给出 ``_HostGlobals`` Protocol（``_host`` 的返回类型）与
  ``_ScanServiceContract``（跨 mixin 互调的方法签名 + 共享类常量），
  让每个 mixin 都能被 mypy 完整检查而不必重复声明。

为什么不干脆 ``_host: Any``：那会让所有 ``self._host.Contract.objects...`` 退化成 ``Any``，
把类型检查在这些最关键的资金/归档路径上全部关掉（实测引入 68 个 ``no-any-return`` 等错误）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID

    from apps.contracts.models import (
        Contract,
        ContractFolderBinding,
        ContractFolderScanSession,
        ContractFolderScanStatus,
    )
    from apps.core.services.bound_folder_scan_service import BoundFolderScanService

    from ._candidate_post_processor import CandidatePostProcessor
    from ._import_pipeline import ImportPipeline


class _HostGlobals(Protocol):
    """``folder_scan_service`` 模块 globals 里**被测试 patch 且被 mixin 引用**的名字。

    每个属性都必须与宿主模块的顶层绑定逐名对应——测试 patch 的就是这些位置。
    """

    # ── 被 patch 的 ORM 模型 ──────────────────────────────────────────
    Contract: type[Contract]
    ContractFolderBinding: type[ContractFolderBinding]
    ContractFolderScanSession: type[ContractFolderScanSession]
    ContractFolderScanStatus: type[ContractFolderScanStatus]

    # ── 被 patch 的 stdlib / 辅助名 ───────────────────────────────────
    Path: type[Path]

    # ── 被 patch 的归档辅助函数 ───────────────────────────────────────
    get_archive_category: Any
    collect_archive_item_options: Any
    collect_work_log_suggestions: Any
    extract_case_info_from_candidates: Any
    apply_case_info_to_contract: Any
    build_task_submission_service: Any
    _looks_voided_filename: Any


class _ScanServiceContract(Protocol):
    """5 个 mixin 共同拼成的完整服务契约（跨 mixin 互调与共享类常量）。"""

    #: 宿主类上的模块 globals 回查入口（宿主侧是只读 @property）
    @property
    def _host(self) -> _HostGlobals: ...

    #: 视为「扫描进行中」的状态集合（定义在宿主类上，被 _SessionQueryMixin 使用）
    _ACTIVE_STATUSES: set[ContractFolderScanStatus]

    #: ``__init__`` 注入的三个协作者（宿主类实例属性）
    _scan_service: BoundFolderScanService
    _post_processor: CandidatePostProcessor
    _import_pipeline: ImportPipeline

    # ── _ScanTaskMixin ───────────────────────────────────────────────
    def start_scan(
        self,
        *,
        contract_id: int,
        started_by: Any | None,
        rescan: bool = False,
        scan_subfolder: str = "",
    ) -> ContractFolderScanSession: ...

    def list_scan_subfolders(self, *, contract_id: int) -> dict[str, Any]: ...

    def run_scan_task(self, *, session_id: str) -> None: ...

    # ── _ImportMixin ─────────────────────────────────────────────────
    def confirm_import(
        self,
        *,
        contract_id: int,
        session_id: UUID,
        items: list[dict[str, Any]],
        work_log_suggestions: list[dict[str, str]] | None = None,
        storage_provider: Any | None = None,
    ) -> dict[str, Any]: ...

    def _auto_detect_supervision_card(self, contract_id: int) -> dict[str, Any]: ...

    def _mark_voided_candidates(self, candidates: list[dict[str, Any]]) -> int: ...

    def _learn_from_import_correction(
        self,
        *,
        candidate: dict[str, Any],
        actual_archive_item_code: str,
        contract_id: int,
    ) -> None: ...

    # ── _ScanScopeMixin ──────────────────────────────────────────────
    def _extract_scan_subfolder(self, payload: dict[str, Any] | None) -> str: ...

    def _resolve_scan_scope(
        self,
        root_folder: str,
        scan_subfolder: str,
        storage_provider: Any | None = None,
    ) -> dict[str, str]: ...

    def _normalize_scan_subfolder(self, scan_subfolder: str) -> str: ...

    def _is_within_root(self, root: Path, target: Path) -> bool: ...

    # ── _SessionQueryMixin ───────────────────────────────────────────
    def get_session(self, *, contract_id: int, session_id: UUID) -> ContractFolderScanSession: ...

    def get_latest_session(self, *, contract_id: int) -> ContractFolderScanSession | None: ...

    def clear_scan_sessions(self, *, contract_id: int) -> int: ...

    def build_status_payload(self, *, session: ContractFolderScanSession) -> dict[str, Any]: ...

    # ── _BindingMixin ────────────────────────────────────────────────
    def _ensure_contract_exists(self, contract_id: int) -> None: ...

    def _get_accessible_binding(self, contract_id: int) -> ContractFolderBinding: ...

    def _resolve_session_storage_provider(self, session: Any) -> Any | None: ...

    def _make_provider_for_binding(self, binding: ContractFolderBinding) -> Any | None: ...

    # ── 宿主类自身 ────────────────────────────────────────────────────
    def _exclude_dir_keywords(self, *, scan_subfolder: str) -> tuple[str, ...]: ...
