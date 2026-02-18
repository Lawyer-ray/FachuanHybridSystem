"""Business logic services."""

from __future__ import annotations

"""
附件上传服务

负责文书重命名、添加附件到案件日志等写操作.
从 DocumentAttachmentService 中拆分出来.
"""


import logging
import os
import re
import shutil
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.core.protocols import ICaseService

logger = logging.getLogger("apps.automation")


class AttachmentUploadService:
    """附件上传服务 - 处理文书重命名和添加附件"""

    def __init__(
        self,
        case_service: ICaseService | None = None,
        renamer: DocumentRenamer | None = None,
    ) -> None:
        self._case_service = case_service
        self._renamer = renamer

    @property
    def case_service(self) -> ICaseService:
        """延迟加载案件服务"""
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    @property
    def renamer(self) -> DocumentRenamer:
        """延迟加载重命名服务"""
        if self._renamer is None:
            from .document_renamer import DocumentRenamer

            self._renamer = DocumentRenamer()
        return self._renamer

    def rename_documents(self, sms: CourtSMS, document_paths: list[str]) -> list[str]:
        """
        重命名文书列表,返回重命名后的路径

        Args:
            sms: CourtSMS 实例
            document_paths: 待重命名的文书路径列表

        Returns:
            重命名后的文书路径列表
        """
        sms_id = cast(int, sms.pk)
        if not document_paths:
            logger.info("短信 %s 无文书需要重命名", sms_id)
            return []

        case_name: str = sms.case.name if sms.case else "未知案件"  # type: ignore[attr-defined]
        received_date = sms.received_at.date()
        renamed_paths: list[str] = []

        logger.info("开始重命名 %d 个文书: SMS ID=%s", len(document_paths), sms_id)

        for file_path in document_paths:
            try:
                if not os.path.exists(file_path):
                    logger.warning("文书文件不存在,跳过: %s", file_path)
                    continue

                original_name = os.path.basename(file_path)

                new_path = self.renamer.rename_with_fallback(
                    file_path, case_name, received_date, original_name=original_name
                )

                renamed_paths.append(new_path)
                logger.info("文书重命名成功: %s", new_path)
            except Exception as e:
                logger.warning("文书重命名失败,保持原名: %s, 错误: %s", file_path, e)
                if os.path.exists(file_path):
                    renamed_paths.append(file_path)

        logger.info("文书重命名完成: SMS ID=%s, 成功重命名 %d 个文书", sms_id, len(renamed_paths))
        return renamed_paths

    def add_to_case_log(self, sms: CourtSMS, file_paths: list[str]) -> bool:
        """将文书附件添加到案件日志"""
        sms_id = cast(int, sms.pk)
        if not sms.case_log or not file_paths:
            logger.warning("短信 %s 没有案件日志或文件路径,无法添加附件", sms_id)
            return False

        try:
            target_dir = os.path.join(settings.MEDIA_ROOT, "case_logs")
            os.makedirs(target_dir, exist_ok=True)

            success_count = sum(1 for fp in file_paths if self._add_single_attachment(fp, target_dir, sms))

            logger.info("附件添加完成: 成功 %d/%d 个", success_count, len(file_paths))
            return success_count > 0
        except Exception as e:
            logger.error("添加附件到案件日志失败: SMS ID=%s, 错误: %s", sms_id, e)
            return False

    def _add_single_attachment(self, file_path: str, target_dir: str, sms: CourtSMS) -> bool:
        """添加单个文书附件到案件日志"""
        try:
            if not os.path.exists(file_path):
                logger.warning("文件不存在,跳过: %s", file_path)
                return False

            renamed_filename = os.path.basename(file_path)
            if "(" not in renamed_filename or ")" not in renamed_filename:
                renamed_filename = self.fix_filename_format(renamed_filename, sms)

            renamed_filename = self._truncate_filename(renamed_filename)
            target_path = os.path.join(target_dir, renamed_filename)

            if os.path.exists(target_path):
                target_path, renamed_filename = self._get_unique_filepath(target_dir, renamed_filename)

            shutil.copy2(file_path, target_path)
            relative_path = f"case_logs/{renamed_filename}"

            if sms.case_log is None:
                raise ValueError(f"短信 {sms.pk} 没有关联的案件日志")
            case_log = sms.case_log
            success = self.case_service.add_case_log_attachment_internal(
                case_log_id=cast(int, case_log.pk), file_path=relative_path, file_name=renamed_filename
            )
            if success:
                logger.info("成功添加文书附件到案件日志: %s", renamed_filename)
            return bool(success)
        except Exception as e:
            logger.warning("添加文书附件失败: %s, 错误: %s", file_path, e)
            return False

    def _truncate_filename(self, filename: str, max_length: int = 200) -> str:
        """确保文件名不超过最大长度"""
        if len(filename) <= max_length:
            return filename
        name_part, ext = os.path.splitext(filename)
        if not ext:
            ext = ".pdf"
        return name_part[: max_length - len(ext)] + ext

    def _get_unique_filepath(self, target_dir: str, filename: str) -> tuple[str, str]:
        """
        获取唯一的文件路径,如果文件已存在则在"收"字后面添加数字后缀

        Args:
            target_dir: 目标目录
            filename: 原始文件名

        Returns:
            tuple: (完整路径, 新文件名)
        """
        match = re.match(r"^(.+收)(\d*)\.(.+)$", filename)

        if match:
            base_name = match.group(1)
            existing_num = match.group(2)
            ext = match.group(3)

            counter = 1
            if existing_num:
                counter = int(existing_num) + 1

            while True:
                new_filename = f"{base_name}{counter}.{ext}"
                new_path = os.path.join(target_dir, new_filename)
                if not os.path.exists(new_path):
                    return new_path, new_filename
                counter += 1
                if counter > 100:
                    break

        # 降级方案:在扩展名前添加数字
        name_part, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_filename = f"{name_part}_{counter}{ext}"
            new_path = os.path.join(target_dir, new_filename)
            if not os.path.exists(new_path):
                return new_path, new_filename
            counter += 1
            if counter > 100:
                import time

                timestamp = int(time.time())
                new_filename = f"{name_part}_{timestamp}{ext}"
                new_path = os.path.join(target_dir, new_filename)
                return new_path, new_filename

    def fix_filename_format(self, filename: str, sms: CourtSMS) -> str:
        """
        修正文件名格式,确保符合预期的格式:标题(案件名称)_YYYYMMDD收.pdf

        Args:
            filename: 原始文件名
            sms: CourtSMS 实例

        Returns:
            修正后的文件名
        """
        try:
            name_without_ext = filename
            if "." in filename:
                name_without_ext = filename.rsplit(".", 1)[0]

            case_name: str = sms.case.name if sms.case else "未知案件"  # type: ignore[attr-defined]
            received_date = sms.received_at.date()
            date_str = received_date.strftime("%Y%m%d")

            case_name = self._sanitize_filename_part(case_name)
            if len(case_name) > 30:
                case_name = case_name[:30]

            title = "司法文书"

            title_patterns: list[Any] = [
                r"(诉讼费用交费通知书|交费通知书)",
                r"(受理案件通知书|案件受理通知书|受理通知书)",
                r"(诉讼权利义务告知书|权利义务告知书)",
                r"(诉讼风险告知书|风险告知书)",
                r"(小额诉讼告知书|诉讼告知书)",
                r"(判决书|裁定书|调解书|决定书|传票|通知书|支付令|告知书)",
            ]

            for pattern in title_patterns:
                match = re.search(pattern, name_without_ext)
                if match:
                    title = match.group(1)
                    break

            fixed_filename = f"{title}({case_name})_{date_str}收.pdf"

            logger.info("文件名格式修正: %s -> %s", filename, fixed_filename)
            return fixed_filename
        except Exception as e:
            logger.warning("修正文件名格式失败: %s, 错误: %s", filename, e)
            case_name = sms.case.name if sms.case else "未知案件"  # type: ignore[attr-defined]
            date_str = sms.received_at.strftime("%Y%m%d")
            return f"司法文书({case_name})_{date_str}收.pdf"

    def _sanitize_filename_part(self, text: str) -> str:
        """
        清理文件名部分,移除非法字符

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        if not text:
            return ""

        illegal_chars = r'[<>:"|?*\\/]'
        text = re.sub(illegal_chars, "", text)
        text = re.sub(r"[()]", "", text)
        text = re.sub(r"[\x00-\x1f\x7f]", "", text)
        text = text.strip(" .")

        return text
