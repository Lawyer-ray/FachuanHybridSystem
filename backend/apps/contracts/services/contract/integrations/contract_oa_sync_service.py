"""合同 OA 信息同步服务。"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.contracts.models import Contract, ContractOASyncSession, ContractOASyncStatus, ContractParty
from apps.core.dependencies.core import build_task_submission_service
from apps.core.infrastructure.sync_async_bridge import run_sync_isolated

from ._oa_field_mixin import _OAFieldMixin
from ._oa_matching_mixin import _OAMatchingMixin
from ._oa_session_mixin import _OASessionMixin
from ._oa_sync_task_mixin import _OASyncTaskMixin

if TYPE_CHECKING:
    from apps.oa_filing.services.oa_scripts.jtn.case_import import JtnCaseImportScript, OAListCaseCandidate
    from apps.organization.models import AccountCredential

logger = logging.getLogger(__name__)


def _is_headless() -> bool:  # pragma: no cover
    """读取 SystemConfig PLAYWRIGHT_HEADED 决定是否无头模式。"""
    from apps.core.services.system_config_service import SystemConfigService

    return SystemConfigService().get_value("PLAYWRIGHT_HEADED", "").lower() not in ("true", "1", "yes")


class ContractOASyncService(
    _OASessionMixin,
    _OASyncTaskMixin,
    _OAMatchingMixin,
    _OAFieldMixin,
):
    """合同 OA 链接与 OA 案件编号同步服务。

    按子域拆为 4 个同目录 mixin（会话 / 同步任务 / 匹配 / 字段回填），
    方法体经 ``self._host`` 回查本模块 globals——测试 7 处按绑定位置打桩的
    patch（``contract_oa_sync_service.Contract`` 等）因此零改动继续命中。
    """

    _ACTIVE_STATUSES = {ContractOASyncStatus.PENDING, ContractOASyncStatus.RUNNING}
    _STALE_RUNNING_MINUTES = 3

    @property
    def _host(self) -> Any:
        """mixin 回查本模块 globals 的唯一入口——测试 patch 靠它继续命中。"""
        return sys.modules[__name__]


def run_contract_oa_sync_task(session_id: int) -> None:  # pragma: no cover
    """Django-Q 任务入口。"""
    # Playwright 同步 API 执行期间会维护事件循环，后续同步 ORM 更新进度时
    # 可能被 Django 误判为 async context。统一经 sync_async_bridge 隔离到
    # 一次性单线程执行，并作用域化放行 async-unsafe 检查。
    service = ContractOASyncService()
    run_sync_isolated(
        service.run_sync_task,
        session_id=session_id,
        timeout=3300,  # 略小于 Q 任务 timeout=3600，留出失败上报余量
        thread_name_prefix="contract-oa-sync",
        allow_async_unsafe=True,
    )
