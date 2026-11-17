"""``ContractOASyncService`` 拆 mixin 后的**静态类型契约**。

本模块只服务 mypy，**不参与运行期**（业务名的 import 全在 ``TYPE_CHECKING`` 下）。

背景
----
``contract_oa_sync_service.py`` 按子域拆成 4 个同目录 mixin（会话 / 同步任务 / 匹配 / 字段回填）。
拆分有一个硬约束：测试有 7 处 ``patch("...contract_oa_sync_service.Contract")`` 这类**按绑定位置**
打桩的写法，方法体若把业务名一起搬走，patch 就全部失效。

因此采用「方法体搬走、业务名经 ``self._host`` 回查宿主模块 globals」的做法：

- 运行期：``_host`` 是宿主类上的 ``@property``，返回 ``sys.modules[__name__]``；
- 静态期：本模块给出 ``_OAHostGlobals``（``_host`` 的返回类型）与 ``_OAServiceContract``
  （跨 mixin 互调的方法签名 + 共享类常量 + 注入的协作者），让每个 mixin 都能被 mypy 完整检查。

为什么不直接 ``_host: Any``：那会让所有 ``self._host.Contract.objects...`` 退化成 ``Any``，
把这些同步路径上的类型检查全部关掉。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from apps.contracts.models import Contract, ContractOASyncSession, ContractOASyncStatus
    from apps.oa_filing.services.oa_scripts.jtn.case_import import JtnCaseImportScript, OAListCaseCandidate
    from apps.organization.models import AccountCredential

    class _TZModule(Protocol):
        """``django.utils.timezone`` 的用到的子集。"""

        def now(self) -> datetime: ...


class _OAHostGlobals(Protocol):
    """``contract_oa_sync_service`` 模块 globals 里**被测试 patch 且被 mixin 引用**的名字。"""

    #: 被 patch 的 ORM 模型
    Contract: type[Contract]
    ContractOASyncSession: type[ContractOASyncSession]
    ContractOASyncStatus: type[ContractOASyncStatus]

    #: 被 patch 的 django.utils.timezone 模块对象
    timezone: Any


class _OAServiceContract(Protocol):
    """4 个 mixin 共同拼成的完整服务契约（跨 mixin 互调与共享类常量）。"""

    #: 宿主类上的模块 globals 回查入口（宿主侧是只读 @property）
    @property
    def _host(self) -> _OAHostGlobals: ...

    #: 视为「同步进行中」的状态集合（宿主类常量，被 _OASessionMixin 使用）
    _ACTIVE_STATUSES: set[ContractOASyncStatus]

    #: 超过该分钟数仍 RUNNING 视为陈旧（宿主类常量）
    _STALE_RUNNING_MINUTES: int

    def list_missing_oa_contracts(self) -> list[dict[str, Any]]: ...

    def create_or_get_active_session(self, *, started_by: Any | None) -> ContractOASyncSession: ...

    def submit_session_task(self, *, session: ContractOASyncSession) -> ContractOASyncSession: ...

    def get_session(self, *, session_id: int) -> ContractOASyncSession | None: ...

    def build_status_payload(self, *, session: ContractOASyncSession) -> dict[str, Any]: ...

    def save_manual_contract_oa_fields(self, *, updates: list[dict[str, Any]]) -> dict[str, Any]: ...

    def run_sync_task(self, *, session_id: int) -> None: ...

    async def _run_sync_inner(
        self,
        *,
        session: ContractOASyncSession,
        credential: Any,
        contracts: list[Contract],
        total_count: int,
    ) -> dict[str, Any]: ...

    async def _search_candidates_with_fallback_keywords(
        self,
        *,
        script: JtnCaseImportScript,
        contract_id: int,
        contract_name: str,
        limit: int,
    ) -> list[OAListCaseCandidate]: ...

    def _filter_candidates_by_contract_name(
        self,
        *,
        contract_name: str,
        candidates: list[OAListCaseCandidate],
    ) -> list[OAListCaseCandidate]: ...

    def _extract_lawsuit_party_tokens(self, contract_name: str) -> tuple[list[str], list[str]]: ...

    def _split_party_tokens(self, party_text: str, *, strip_dispute: bool) -> list[str]: ...

    def _build_relaxed_party_markers(self, tokens: list[str]) -> list[str]: ...

    def _normalize_match_text(self, value: str) -> str: ...

    def _build_name_search_keywords(self, contract_name: str, contract_id: int = 0) -> list[str]: ...

    def _build_party_name_keywords(self, *, contract_id: int) -> list[str]: ...

    def _is_stale_active_session(self, session: ContractOASyncSession) -> bool: ...

    def _build_missing_contract_queryset(self) -> Any: ...

    def _serialize_missing_contracts(self, contracts: list[Contract]) -> list[dict[str, Any]]: ...

    def _fill_contract_oa_fields(self, *, contract: Contract, candidate: OAListCaseCandidate) -> None: ...

    def _resolve_oa_credential(self, *, lawyer_id: int | None) -> AccountCredential: ...

    def _extract_sso_login_url(self, text: str) -> str: ...

    def _update_session(self, session: ContractOASyncSession, **fields: Any) -> None: ...
