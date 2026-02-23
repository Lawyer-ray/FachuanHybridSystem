"""
外部模板分析服务

负责模板上传校验、文件保存、版本管理。
结构提取和 LLM 分析方法将在后续任务 (6.2, 6.3) 中实现。

Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .fingerprint_service import FingerprintService

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile

    from apps.documents.models.external_template import ExternalTemplate
    from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger: logging.Logger = logging.getLogger(__name__)


class AnalysisService:
    """外部模板分析服务：上传校验 + 结构提取 + LLM 字段映射"""

    MAX_FILE_SIZE: ClassVar[int] = 20 * 1024 * 1024  # 20MB

    def __init__(
        self,
        fingerprint_service: FingerprintService,
        llm_service: Any,
        placeholder_registry: PlaceholderRegistry,
    ) -> None:
        self._fingerprint_service = fingerprint_service
        self._llm_service = llm_service
        self._placeholder_registry = placeholder_registry

    # ------------------------------------------------------------------
    # 上传与校验
    # ------------------------------------------------------------------

    def upload_template(
        self,
        file: UploadedFile,
        name: str,
        category: str,
        source_type: str,
        court_id: int | None,
        organization_name: str,
        uploaded_by: Any,
    ) -> ExternalTemplate:
        """
        上传外部模板：
        1. 校验 .docx 格式、文件大小 ≤ 20MB
        2. 保存文件（UUID 重命名）
        3. 验证 python-docx 可解析
        4. 处理版本管理（同法院/机构 + 类别组合自增版本号）
        5. 创建 ExternalTemplate 记录
        """
        from apps.documents.models.external_template import ExternalTemplate

        self._validate_file(file)

        law_firm_id: int = uploaded_by.law_firm_id
        abs_path, rel_path = self._save_file(file, law_firm_id)

        try:
            self._validate_parseable(abs_path)
        except ValidationError:
            # 解析失败时删除已保存的文件
            if abs_path.exists():
                abs_path.unlink()
                logger.info("已删除无法解析的文件: %s", abs_path)
            raise

        file_size: int = file.size if file.size is not None else 0
        original_filename: str = file.name if file.name else ""

        with transaction.atomic():
            version, deactivated = self._handle_versioning(
                law_firm_id=law_firm_id,
                court_id=court_id,
                category=category,
                source_type=source_type,
                organization_name=organization_name,
            )

            template: ExternalTemplate = ExternalTemplate.objects.create(
                name=name,
                category=category,
                source_type=source_type,
                court_id=court_id,
                organization_name=organization_name,
                file_path=rel_path,
                original_filename=original_filename,
                file_size=file_size,
                version=version,
                is_active=True,
                uploaded_by=uploaded_by,
                law_firm_id=law_firm_id,
            )

        logger.info(
            "模板上传成功: id=%d, name=%s, version=%d, deactivated=%d",
            template.id,
            template.name,
            version,
            deactivated,
        )
        return template

    def _validate_file(self, file: UploadedFile) -> None:
        """校验 .docx 格式和文件大小"""
        filename: str = file.name if file.name else ""
        if not filename.lower().endswith(".docx"):
            logger.info("文件格式校验失败: %s", filename)
            raise ValidationError(_("仅支持 .docx 格式"))

        file_size: int = file.size if file.size is not None else 0
        if file_size > self.MAX_FILE_SIZE:
            logger.info(
                "文件大小超出限制: %s, size=%d",
                filename,
                file_size,
            )
            raise ValidationError(_("文件大小超出限制"))

    def _validate_parseable(self, file_path: Path) -> None:
        """尝试 python-docx 打开文件，验证可解析性"""
        try:
            from docx import Document as DocxDocument

            DocxDocument(str(file_path))
        except Exception as exc:
            logger.info(
                "文件无法解析: %s, error=%s",
                file_path.name,
                str(exc),
            )
            raise ValidationError(
                _("文件无法解析，请检查文件是否损坏或加密")
            ) from exc

    def _save_file(
        self, file: UploadedFile, law_firm_id: int
    ) -> tuple[Path, str]:
        """
        UUID 重命名保存文件

        Returns:
            (绝对路径, 相对于 MEDIA_ROOT 的路径)
        """
        media_root = Path(settings.MEDIA_ROOT)
        rel_dir = Path("documents") / "external_templates" / str(law_firm_id)
        abs_dir = media_root / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)

        new_filename = f"{uuid.uuid4()}.docx"
        rel_path = rel_dir / new_filename
        abs_path = media_root / rel_path

        with abs_path.open("wb") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        logger.info("文件已保存: %s", abs_path)
        return abs_path, str(rel_path)

    # ------------------------------------------------------------------
    # 版本管理
    # ------------------------------------------------------------------

    def _handle_versioning(
        self,
        *,
        law_firm_id: int,
        court_id: int | None,
        category: str,
        source_type: str,
        organization_name: str,
    ) -> tuple[int, int]:
        """
        处理版本管理：同一来源 + 类别组合自增版本号，旧版本 is_active=False

        Returns:
            (新版本号, 被停用的旧版本数量)
        """
        from apps.documents.models.external_template import ExternalTemplate

        existing = ExternalTemplate.objects.filter(
            law_firm_id=law_firm_id,
            category=category,
        )

        if court_id is not None:
            existing = existing.filter(court_id=court_id)
        else:
            existing = existing.filter(
                court__isnull=True,
                organization_name=organization_name,
            )

        max_version: int | None = existing.order_by("-version").values_list(
            "version", flat=True
        ).first()

        new_version: int = (max_version or 0) + 1

        deactivated: int = existing.filter(is_active=True).update(
            is_active=False
        )

        return new_version, deactivated
