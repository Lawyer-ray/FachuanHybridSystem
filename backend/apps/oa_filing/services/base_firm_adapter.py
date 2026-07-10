"""OA 系统适配器协议。

每个律所 OA 系统实现一组 Protocol，由 ScriptExecutorService 统一调度。
新增律所只需：
1. 在 oa_scripts/<firm>/ 下创建 adapter.py 实现这些 Protocol
2. 在 oa_firm_registry.py 中注册
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FilingAdapter(Protocol):
    """立案适配器协议。"""

    async def execute_filing(
        self,
        session: Any,
        credential: Any,
        contract_id: int,
        case_id: int | None,
    ) -> None:
        """执行立案操作。"""
        ...


@runtime_checkable
class StampAdapter(Protocol):
    """盖章适配器协议。"""

    async def execute_stamp(self, session: Any) -> None:
        """执行盖章申请。从 session 中读取凭证和表单数据。"""
        ...


@runtime_checkable
class ArchiveAdapter(Protocol):
    """归档适配器协议。"""

    async def execute_archive(self, session: Any) -> None:
        """执行归档材料提交。从 session 中读取凭证和文件路径。"""
        ...

    async def open_oa_page(
        self,
        credential: Any,
        oa_case_number: str,
        description: str,
    ) -> None:
        """打开 OA 归档页面，填写案件编号和小结，保持浏览器打开。"""
        ...

    async def open_invoice_page(
        self,
        credential: Any,
        oa_case_number: str,
    ) -> None:
        """打开 OA 发票页面，输入案件编号并跳转到开票页面，保持浏览器打开。"""
        ...


@runtime_checkable
class CaseImportAdapter(Protocol):
    """案件导入适配器协议。"""

    async def execute_case_import(self, session: Any) -> None:
        """执行案件导入。"""
        ...

    async def fetch_case_detail(self, case_no: str, credential: Any) -> Any | None:
        """从 OA 获取案件详情，返回 OACaseData 或 None。"""
        ...

    def search_cases(
        self,
        case_nos: list[str],
        credential: Any,
        *,
        workers: int = 2,
        headless: bool = True,
        progress_callback: Any = None,
    ) -> Any:
        """批量搜索案件，返回 AsyncGenerator[(case_no, OACaseData | None)]。"""
        ...

    def build_case_detail_url(self, oa_data: Any) -> str:
        """构建 OA 案件详情页 URL。"""
        ...


@runtime_checkable
class ClientImportAdapter(Protocol):
    """客户导入适配器协议。"""

    async def execute_client_import(self, session: Any, *, headless: bool, limit: int | None) -> None:
        """执行客户导入。"""
        ...

    def iter_customers(self, session: Any, *, headless: bool, limit: int | None, progress_callback: Any = None) -> Any:
        """返回 AsyncGenerator[OACustomerData, None]，逐条 yield 客户数据。"""
        ...
