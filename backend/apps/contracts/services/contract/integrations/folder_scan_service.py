"""合同文件夹自动捕获服务。

按子域拆为 5 个 mixin（**同目录**，方法体经 ``self._host`` 回查本模块 globals）：

- ``_ScanTaskMixin``       扫描启动 / 子文件夹列举 / Django-Q 任务执行
- ``_ImportMixin``         确认导入 / 监督卡检测 / 作废票标记 / 导入纠错学习
- ``_ScanScopeMixin``      子文件夹解析 / 越界校验 / 相对路径归一化
- ``_SessionQueryMixin``   会话读取 / 清空 / 状态载荷装配
- ``_BindingMixin``        合同存在性 / 可访问绑定 / 云存储 provider 解析

.. important::
   **为什么是 mixin 而不是拆成同名子包**：测试有 53 处 patch 指向本模块的**具体绑定位置**
   （``folder_scan_service.Contract`` 24 处、``.ContractFolderScanSession`` 11 处等）。
   拆成同名包后这些名字的绑定位置改变、patch 全部失效，需同步改 6 个测试文件；
   mixin 方案把方法体搬走但保留本模块为唯一定义点，**零测试改动**。

   mixin 内的纪律：引用被 patch 的名字一律写 ``self._host.Contract``，禁裸名
   （裸名在 mixin 模块 globals 里不存在，会 NameError）。
"""

from __future__ import annotations

import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import Contract, ContractFolderBinding, ContractFolderScanSession, ContractFolderScanStatus
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.contract.integrations.archive_classifier import (
    collect_archive_item_options,
    collect_work_log_suggestions,
)
from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.bound_folder_scan_service import BoundFolderScanService

from ._binding_mixin import _BindingMixin
from ._candidate_post_processor import CandidatePostProcessor
from ._import_mixin import _ImportMixin
from ._import_pipeline import ImportPipeline
from ._scan_scope_mixin import _ScanScopeMixin
from ._scan_task_mixin import _ScanTaskMixin
from ._session_query_mixin import _SessionQueryMixin
from .case_info_extraction_service import apply_case_info_to_contract, extract_case_info_from_candidates

logger = logging.getLogger(__name__)


class ContractFolderScanService(
    _ScanTaskMixin,
    _ImportMixin,
    _ScanScopeMixin,
    _SessionQueryMixin,
    _BindingMixin,
):
    """合同自动捕获扫描、轮询、确认导入服务。"""

    @property
    def _host(self) -> Any:
        """mixin 回查本模块 globals 的唯一入口——测试 patch 靠它继续命中。"""
        return sys.modules[__name__]

    _ACTIVE_STATUSES = {
        ContractFolderScanStatus.PENDING,
        ContractFolderScanStatus.RUNNING,
        ContractFolderScanStatus.CLASSIFYING,
    }

    # 全局扫描（未指定子文件夹）默认跳过的目录关键词：客户资料是当事人身份材料，
    # 不是归档清单项；需要时在弹窗显式选中该子文件夹单独扫描
    _GLOBAL_EXCLUDE_DIR_KEYWORDS: tuple[str, ...] = ("客户资料",)

    # 任何扫描范围都不进去的目录：`已冲红/` 放的是作废的原票与红票（§3.5 闸 2）。
    #
    # 不放进上面那个关键词集：那个只在「未指定子文件夹」时生效（选中 `3-发票`
    # 单独扫时会被豁免）。作废票不是“默认藏起来”而是“永远不能进归档清单”，
    # 所以它对所有扫描范围都生效。
    _ALWAYS_EXCLUDE_DIR_KEYWORDS: tuple[str, ...] = ("已冲红",)

    def _exclude_dir_keywords(self, *, scan_subfolder: str) -> tuple[str, ...]:
        """按扫描范围给出目录排除关键词（全局扫描要同时躲开两组，子文件夹扫描仍躲作废目录）。"""
        keywords = self._ALWAYS_EXCLUDE_DIR_KEYWORDS
        if not scan_subfolder:
            keywords = keywords + self._GLOBAL_EXCLUDE_DIR_KEYWORDS
        return keywords

    def __init__(self, *, scan_service: BoundFolderScanService | None = None) -> None:
        self._scan_service = scan_service or BoundFolderScanService()
        self._post_processor = CandidatePostProcessor(self._scan_service)
        self._import_pipeline = ImportPipeline()


def run_contract_folder_scan_task(session_id: str) -> None:  # pragma: no cover
    """Django-Q 任务入口。"""
    ContractFolderScanService().run_scan_task(session_id=session_id)


def _normalize_docx_name(filename: str) -> str:
    """标准化文件名用于关键词匹配。"""
    return re.sub(r"\s+", "", str(filename or "").strip().lower())


#: 红票文件名尾标（与 ``invoice_file_service.VOIDED_NAME_MARKER`` 同一命名规则）
VOIDED_NAME_MARKER = "红字开具"


def _looks_voided_filename(filename: str) -> bool:
    """文件名是不是一张作废红票（含「红字开具」）。

    先 NFKC 归一化再比对，避免全角/兼容字符差异导致漏判。
    """
    return VOIDED_NAME_MARKER in unicodedata.normalize("NFKC", str(filename or ""))
