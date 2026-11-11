"""客户转交材料的入库服务（非法院通道送达）。

业务背景
--------
案件材料并不总是经法院通道（短信里的下载链接 + 爬虫）送达。常见情形是客户先
收到法院/对方发来的材料，再用微信转给律师。这类材料同样需要走「解析 → 匹配
案件 → 重命名归档 → 群通知」的既有链路，因此这里只解决**来源**问题：

    用户拖入的本地文件 → 清洗/校验/落盘 → 写入 CourtSMS.document_file_paths

落盘后的记录与短信通道的记录在数据层完全同构（同样是一条 CourtSMS，只是
download_links 为空、document_file_paths 已就位），下游各阶段无需任何特判：

- ``_process_downloading_or_matching``：无下载链接 → 直接进入 matching；
- ``_process_matching``：``_get_document_paths_for_extraction`` 从
  ``document_file_paths`` 抽案号/当事人；
- ``_process_renaming``：无 ``scraper_task`` 时回落到 ``document_file_paths``；
- ``CourtSMSDocumentReferenceService.collect``：``_collect_from_sms_paths`` 已支持。

设计约束
--------
- 落盘必须走 ``storage_service.save_uploaded_file``（清洗文件名、扩展名白名单、
  大小上限、可执行文件魔数检测、路径收敛在 MEDIA_ROOT 内），禁止直写 media。
- 单个文件失败不阻断整批：微信导出的材料常混有 ``.heic`` / ``.txt`` 等不受支持的
  格式，整批拒绝会让律师反复试错。成功入库的照常处理，被跳过的逐条回报原因。
- 全部文件都不可用（空批次 / 全部格式不符）则直接拒绝，不建空记录。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.storage_service import resolve_media_path, save_uploaded_file, to_media_abs

logger = logging.getLogger("apps.automation")

# 与 storage_service.ALLOWED_EXTENSIONS 对齐，但保持本模块自洽（额外接受微信导出常见 .bmp）
_INTAKE_ALLOWED_EXTENSIONS: list[str] = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".bmp"]

# 单个材料上限：法院文书 PDF 常达数十 MB（含扫描件），50MB 与文档解析模块同口径
_INTAKE_MAX_SIZE_BYTES: int = 50 * 1024 * 1024

# 微信图片文件名形如「微信图片_20251110103000.jpg」，用它做标题毫无信息量。
# 判定为「无语义文件名」后，标题栏交由后续 LLM 识别文书标题（失败再降级原名）。
_WECHAT_FILENAME_PATTERN = re.compile(r"^(微信图片|微信截图|微信文件|mmexport|wx_camera|image|img|scan)[_\-\d]", re.I)


class CourtSMSDocumentIntakeService:
    """把客户转交的本地材料落盘并登记到短信记录的文书引用字段。"""

    allowed_extensions = _INTAKE_ALLOWED_EXTENSIONS
    max_size_bytes = _INTAKE_MAX_SIZE_BYTES

    def save_materials(self, sms_id: int, uploads: list[Any]) -> dict[str, Any]:
        """落盘一批材料并合并进 ``CourtSMS.document_file_paths``。

        Args:
            sms_id: 目标短信记录 ID（调用方已建记录）。
            uploads: Django ``UploadedFile`` 列表（multipart ``files`` 字段）。

        Returns:
            ``{"saved": [文件名...], "skipped": [{"name": str, "reason": str}...]}``

        Raises:
            ValidationException: 一个文件都没能入库（空批次 / 全部不可用 / 记录不存在）。
        """
        from apps.automation.models import CourtSMS

        if not uploads:
            raise ValidationException(
                message="请至少拖入一个案件材料文件",
                code="EMPTY_MATERIAL_BATCH",
                errors={"files": "文件列表为空"},
            )

        saved_paths: list[str] = []
        saved_names: list[str] = []
        skipped: list[dict[str, str]] = []

        for upload in uploads:
            display_name = str(getattr(upload, "name", "") or "")
            try:
                rel_path, safe_name = save_uploaded_file(
                    uploaded_file=upload,
                    rel_dir=MediaEntity.AUTOMATION_UPLOADS,
                    allowed_extensions=self.allowed_extensions,
                    max_size_bytes=self.max_size_bytes,
                )
            except ValidationException as exc:
                logger.info("客户材料被跳过（校验未通过）: %s, 原因: %s", display_name, exc.message)
                skipped.append({"name": display_name, "reason": str(exc.message)})
                continue
            except Exception as exc:  # pragma: no cover - 磁盘/存储层异常
                logger.exception("客户材料落盘失败: %s", display_name)
                skipped.append({"name": display_name, "reason": f"保存失败: {exc}"})
                continue

            saved_paths.append(rel_path)
            saved_names.append(self._to_display_name(display_name, safe_name))
            logger.info("客户材料已落盘: %s -> %s", display_name, rel_path)

        if not saved_paths:
            raise ValidationException(
                message="拖入的文件都不受支持，请上传 PDF / Word / 图片",
                code="ALL_MATERIALS_REJECTED",
                errors={"files": "、".join(f"{item['name']}({item['reason']})" for item in skipped)},
            )

        self._attach_paths(sms_id, saved_paths, saved_names)
        return {"saved": saved_names, "skipped": skipped}

    def build_content_placeholder(self, saved_names: list[str]) -> str:
        """文件通道没有短信原文，用材料清单填充 ``CourtSMS.content``。

        ``content`` 是 TextField 且历史逻辑（归档 markdown、admin 列表、全局
        trigram 检索）都以它为主键信息，留空会让归档副本出现「短信原文: (空)」。
        这里生成一行可读清单，让归档与后台检索都有内容可用。
        """
        stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
        listing = "、".join(saved_names) if saved_names else "（无）"
        return f"【客户转交材料】{stamp} 收到 {len(saved_names)} 个文件：{listing}"

    # ------------------------------------------------------------------
    # 内部：路径与标题
    # ------------------------------------------------------------------

    def _attach_paths(self, sms_id: int, rel_paths: list[str], saved_names: list[str]) -> None:
        """把落盘路径合并进短信记录（去重 + 存 media 绝对路径）。

        ``resolve_media_path`` 在拔存储路径时接受相对/绝对两种写法，但下游
        ``DocumentRenamer`` 会把文件**物理重命名**后回写引用，绝对路径更稳定
        （相对路径在 cwd 变化时会解析到别处）。
        """
        from apps.automation.models import CourtSMS, CourtSMSStatus

        try:
            sms = CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist as exc:
            raise ValidationException(
                message="短信记录不存在，材料无法登记",
                code="SMS_NOT_FOUND",
                errors={"sms_id": sms_id},
            ) from exc

        abs_paths = [str(to_media_abs(p)) for p in rel_paths]
        existing = sms.document_file_paths if isinstance(sms.document_file_paths, list) else []
        merged = list(dict.fromkeys([*existing, *abs_paths]))

        # 已有 content 时保留原文并按行追加材料清单；文件通道新建记录时 content
        # 就是占位清单，由调用方（submit_sms）一次性写入，这里只做兜底。
        update_fields = ["document_file_paths", "updated_at"]
        if not (sms.content or "").strip():
            sms.content = self.build_content_placeholder(saved_names)
            update_fields.append("content")

        # 有下载链接的记录不能抢走它的 downloading 流程
        if not sms.download_links and sms.status in (CourtSMSStatus.PENDING, CourtSMSStatus.PARSING):
            sms.status = CourtSMSStatus.MATCHING
            update_fields.append("status")

        sms.document_file_paths = merged
        sms.save(update_fields=update_fields)
        logger.info("短信 %s 登记客户材料 %s 个（累计 %s 个引用）", sms_id, len(abs_paths), len(merged))

    def _to_display_name(self, original_name: str, safe_name: str) -> str:
        """原始文件名可用就用原始名，被清洗掉信息时退回存储名。"""
        stem = original_name.rsplit("/", 1)[-1].strip() or safe_name
        return stem

    @classmethod
    def is_meaningful_filename(cls, filename: str) -> bool:
        """文件名是否含可读信息（用于决定重命名时是否直接沿用原标题）。"""
        stem = filename.rsplit(".", 1)[0].strip()
        if len(stem) < 3:
            return False
        return not _WECHAT_FILENAME_PATTERN.match(stem)

    def cleanup_paths(self, paths: list[str]) -> int:
        """删除本通道落盘的文件，返回实际删除数。

        供 ``CourtSMS`` 的 post_delete 信号等调用方使用；下载原件归 ScraperTask
        的 post_delete 信号管理，这里通过 ``_is_intake_path`` 不越权删。
        """
        from apps.core.services.storage_service import delete_media_file

        removed = 0
        for raw in paths:
            if not raw or not self._is_intake_path(raw):
                continue
            if delete_media_file(raw):
                removed += 1
        return removed

    def _is_intake_path(self, raw_path: str) -> bool:
        """判断路径是否位于本通道的落盘目录下。"""
        try:
            candidate = resolve_media_path(raw_path).resolve(strict=False)
            intake_root = (Path(settings.MEDIA_ROOT) / MediaEntity.AUTOMATION_UPLOADS).resolve(strict=False)
        except Exception:  # pragma: no cover - 异常路径不删，宁留勿误删
            return False
        return candidate.is_relative_to(intake_root)


__all__ = ["CourtSMSDocumentIntakeService"]
