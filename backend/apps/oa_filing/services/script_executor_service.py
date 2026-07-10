"""OA 立案/盖章/归档/导入 通用调度器。

通过 oa_firm_registry 按 site_name 分发到对应律所适配器。
本文件不含任何律所特有逻辑。
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.apps import apps as django_apps

from .oa_firm_registry import create_adapter

logger = logging.getLogger("apps.oa_filing")

_executor = ThreadPoolExecutor(max_workers=2)


class ScriptExecutorService:
    """OA 通用调度器。按 site_name 分发到对应律所适配器。"""

    # ------------------------------------------------------------------
    # Session 查询（公共）
    # ------------------------------------------------------------------

    def get_session(self, session_id: int) -> Any:
        from apps.oa_filing.models import FilingSession

        return FilingSession.objects.get(pk=session_id)

    def get_stamp_session(self, session_id: int) -> Any:
        from apps.oa_filing.models import StampSession

        return StampSession.objects.get(pk=session_id)

    def get_archive_session(self, session_id: int) -> Any:
        from apps.oa_filing.models import ArchiveSession

        return ArchiveSession.objects.get(pk=session_id)

    # ------------------------------------------------------------------
    # 凭证查找（公共）
    # ------------------------------------------------------------------

    @staticmethod
    def _find_credential(user: Any, site_name: str) -> Any:
        """查找用户在指定站点的登录凭证。"""
        credential_model = django_apps.get_model("organization", "AccountCredential")
        return credential_model.objects.filter(lawyer=user, site_name=site_name).first()

    # ------------------------------------------------------------------
    # 立案
    # ------------------------------------------------------------------

    def execute(
        self,
        site_name: str,
        contract_id: int,
        case_id: int | None,
        user: Any,
    ) -> Any:
        from apps.oa_filing.models import FilingSession, SessionStatus
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        credential = self._find_credential(user, site_name)
        if credential is None:
            raise ScriptExecutionError(f"未找到匹配凭证: 站点名称={site_name}")

        session = FilingSession.objects.create(
            contract_id=contract_id,
            case_id=case_id,
            oa_config=None,
            credential=credential,
            user=user,
            status=SessionStatus.IN_PROGRESS,
        )
        logger.info("开始立案: session=%d, site=%s", session.id, site_name)

        _executor.submit(self._run_in_thread, session.id, site_name, credential, contract_id, case_id)
        return FilingSession.objects.get(pk=session.id)

    def _run_in_thread(
        self,
        session_id: int,
        site_name: str,
        credential: Any,
        contract_id: int,
        case_id: int | None,
    ) -> None:
        from apps.oa_filing.models import FilingSession, SessionStatus

        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        try:
            asyncio.run(self._dispatch_filing(site_name, credential, contract_id, case_id))
            FilingSession.objects.filter(pk=session_id).update(status=SessionStatus.COMPLETED)
            logger.info("立案完成: session=%d", session_id)
        except Exception as exc:
            FilingSession.objects.filter(pk=session_id).update(status=SessionStatus.FAILED, error_message=str(exc))
            logger.error("立案失败: session=%d, error=%s", session_id, exc)

    async def _dispatch_filing(self, site_name: str, credential: Any, contract_id: int, case_id: int | None) -> None:
        adapter = create_adapter(site_name, str(credential.account), str(credential.password))
        await adapter.execute_filing(session=None, credential=credential, contract_id=contract_id, case_id=case_id)

    # ------------------------------------------------------------------
    # 盖章
    # ------------------------------------------------------------------

    def execute_stamp(self, file_path: str, user: Any, site_name: str = "金诚同达OA") -> Any:
        from apps.oa_filing.models import StampSession, StampSessionStatus
        from apps.oa_filing.services.stamp_lookup_service import StampLookupService

        lookup = StampLookupService.lookup_by_file_path(file_path)
        credential = self._find_credential(user, site_name)

        session = StampSession.objects.create(
            contract_id=lookup.contract_id,
            credential=credential,
            user=user,
            oa_case_number=lookup.oa_case_number,
            file_path=file_path,
            status=StampSessionStatus.IN_PROGRESS,
        )
        logger.info("开始盖章: session=%d, oa_no=%s", session.id, lookup.oa_case_number)
        _executor.submit(self._run_stamp_in_thread, session.id, site_name)
        return StampSession.objects.get(pk=session.id)

    def _run_stamp_in_thread(self, session_id: int, site_name: str) -> None:
        from apps.oa_filing.models import StampSession, StampSessionStatus

        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        try:
            asyncio.run(self._dispatch_stamp(session_id, site_name))
            StampSession.objects.filter(pk=session_id).update(status=StampSessionStatus.COMPLETED)
            logger.info("盖章完成: session=%d", session_id)
        except Exception as exc:
            StampSession.objects.filter(pk=session_id).update(status=StampSessionStatus.FAILED, error_message=str(exc))
            logger.error("盖章失败: session=%d, error=%s", session_id, exc)

    async def _dispatch_stamp(self, session_id: int, site_name: str) -> None:
        from apps.oa_filing.models import StampSession

        session = await StampSession.objects.select_related("credential").aget(pk=session_id)
        adapter = create_adapter(site_name, str(session.credential.account), str(session.credential.password))
        await adapter.execute_stamp(session)

    # ------------------------------------------------------------------
    # 归档
    # ------------------------------------------------------------------

    def execute_archive(self, file_paths: list[str], user: Any, site_name: str = "金诚同达OA") -> Any:
        from apps.oa_filing.models import ArchiveSession, ArchiveSessionStatus
        from apps.oa_filing.services.stamp_lookup_service import StampLookupService

        lookup = StampLookupService.lookup_by_file_path(file_paths[0])
        credential = self._find_credential(user, site_name)

        session = ArchiveSession.objects.create(
            contract_id=lookup.contract_id,
            credential=credential,
            user=user,
            oa_case_number=lookup.oa_case_number,
            file_paths=file_paths,
            status=ArchiveSessionStatus.IN_PROGRESS,
        )
        logger.info("开始归档: session=%d, oa_no=%s", session.id, lookup.oa_case_number)
        _executor.submit(self._run_archive_in_thread, session.id, site_name)
        return ArchiveSession.objects.get(pk=session.id)

    def _run_archive_in_thread(self, session_id: int, site_name: str) -> None:
        from apps.oa_filing.models import ArchiveSession, ArchiveSessionStatus

        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        try:
            asyncio.run(self._dispatch_archive(session_id, site_name))
            ArchiveSession.objects.filter(pk=session_id).update(status=ArchiveSessionStatus.COMPLETED)
            logger.info("归档完成: session=%d", session_id)
        except Exception as exc:
            ArchiveSession.objects.filter(pk=session_id).update(
                status=ArchiveSessionStatus.FAILED, error_message=str(exc)
            )
            logger.error("归档失败: session=%d, error=%s", session_id, exc)

    async def _dispatch_archive(self, session_id: int, site_name: str) -> None:
        from apps.oa_filing.models import ArchiveSession

        session = await ArchiveSession.objects.select_related("credential").aget(pk=session_id)
        adapter = create_adapter(site_name, str(session.credential.account), str(session.credential.password))
        await adapter.execute_archive(session)

    # ------------------------------------------------------------------
    # 打开 OA 页面
    # ------------------------------------------------------------------

    def open_oa_page(
        self, contract_id: int, user: Any, description: str = "详见卷宗", site_name: str = "金诚同达OA"
    ) -> None:
        """打开 OA 归档页面，填写案件编号和小结，保持浏览器打开。"""
        from apps.contracts.models import Contract

        credential = self._find_credential(user, site_name)
        if credential is None:
            raise RuntimeError(f"未找到匹配凭证: 站点名称={site_name}")

        contract = Contract.objects.filter(pk=contract_id).first()
        oa_case_number = contract.law_firm_oa_case_number if contract else ""

        _executor.submit(
            self._run_open_oa_in_thread,
            site_name,
            credential,
            oa_case_number,
            description,
        )

    def _run_open_oa_in_thread(
        self,
        site_name: str,
        credential: Any,
        oa_case_number: str,
        description: str,
    ) -> None:
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        try:
            adapter = create_adapter(site_name, str(credential.account), str(credential.password))
            asyncio.run(adapter.open_oa_page(credential, oa_case_number, description))
            logger.info("OA 页面已打开")
        except Exception as exc:
            logger.error("打开 OA 页面失败: %s", exc, exc_info=True)
