"""法院短信关联文书重命名服务。

承载 court_sms_api rename 端点下沉的业务：短信定位、文书引用校验、
文件名清洗与冲突检查、重命名执行、引用路径同步。
返回轻量结果对象（CourtSMSDocumentRenameResult），响应 Schema 由 API 层组装。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
from apps.automation.services.sms.court_sms_repository import CourtSMSRepository
from apps.core.exceptions import NotFoundError, ValidationException

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS

logger = logging.getLogger(__name__)

# 文件名主体中的非法字符（Windows 保留集），清洗后为空则拒绝
_ILLEGAL_STEM_CHARS = re.compile(r'[\\/:*?"<>|]')


@dataclass
class CourtSMSDocumentRenameResult:
    """重命名结果（API 层据此组装响应 Schema）。"""

    success: bool
    message: str | None = None
    new_name: str | None = None


class CourtSMSDocumentRenameService:
    """法院短信关联文书的重命名与引用同步。"""

    def __init__(
        self,
        *,
        repository: CourtSMSRepository | None = None,
        reference_service: CourtSMSDocumentReferenceService | None = None,
    ) -> None:
        self._repository = repository or CourtSMSRepository()
        self._reference_service = reference_service or CourtSMSDocumentReferenceService()

    async def rename_document(self, *, sms_id: int, ref_index: int, new_stem: str) -> CourtSMSDocumentRenameResult:
        """重命名单个关联文书并同步引用路径。

        Raises:
            NotFoundError: 短信记录不存在（HTTP 404）
            ValidationException: 索引越界 / 文件缺失 / 文件名非法 / 目标已存在（HTTP 400）
        """
        sms = await sync_to_async(self._repository.get_by_id_or_none)(sms_id=sms_id)
        if sms is None:
            raise NotFoundError("短信记录不存在")

        references = await sync_to_async(self._reference_service.collect)(sms)

        if ref_index < 0 or ref_index >= len(references):
            raise ValidationException("文书索引超出范围", code="DOC_INDEX_OUT_OF_RANGE")

        ref = references[ref_index]
        file_path = Path(ref.file_path)
        if not file_path.exists() or not file_path.is_file():
            raise ValidationException("文书文件不存在", code="DOC_FILE_NOT_FOUND")

        raw_stem = str(new_stem or "").strip()
        if not raw_stem:
            raise ValidationException("文件名不能为空", code="EMPTY_FILENAME")
        if "." in raw_stem:
            raise ValidationException("只能修改文件名，不能修改扩展名", code="FILENAME_HAS_EXTENSION")

        cleaned_stem = _ILLEGAL_STEM_CHARS.sub("", raw_stem).strip()
        if not cleaned_stem:
            raise ValidationException("文件名包含非法字符", code="INVALID_FILENAME")

        new_path = file_path.with_name(f"{cleaned_stem}{file_path.suffix}")
        if new_path == file_path:
            return CourtSMSDocumentRenameResult(success=True, message="文件名未变化")
        if new_path.exists():
            raise ValidationException(f"目标文件已存在：{new_path.name}", code="TARGET_EXISTS")

        old_abs = str(file_path.resolve())
        await asyncio.to_thread(file_path.rename, new_path)
        new_abs = str(new_path.resolve())

        await self._sync_document_references(
            sms=sms, old_abs=old_abs, new_abs=new_abs, court_document_id=ref.court_document_id
        )

        logger.info("法院短信文书已重命名: sms_id=%s, %s -> %s", sms_id, old_abs, new_abs)
        return CourtSMSDocumentRenameResult(success=True, new_name=new_path.name)

    async def _sync_document_references(
        self, *, sms: CourtSMS, old_abs: str, new_abs: str, court_document_id: int | None
    ) -> None:
        """同步重命名后的引用路径（短信/爬虫结果/案件日志附件/CourtDocument）。

        引用同步逻辑位于 CourtSMSDocumentReferenceService（Service 层），
        与 admin 手动重命名、短信自动重命名两条路径共用同一实现。
        """
        await sync_to_async(self._reference_service.sync_document_references)(sms, old_abs, new_abs, court_document_id)
