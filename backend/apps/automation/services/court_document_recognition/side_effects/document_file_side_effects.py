"""Side effect handlers."""

import logging
from datetime import date

from apps.automation.services.court_document_recognition.data_classes import DocumentType
from apps.core.path import Path

logger = logging.getLogger("apps.automation")


class DocumentFileSideEffects:
    def rename_for_manual_bind(self, *, file_path: str, document_type: DocumentType, case_name: str) -> str:
        try:
            from apps.automation.services.sms.document_renamer import DocumentRenamer

            original_path = Path(file_path)
            if not original_path.exists():
                logger.warning(
                    "文件不存在,无法重命名", extra={"action": "rename_for_manual_bind", "file_path": file_path}
                )
                return file_path

            type_titles = {
                DocumentType.SUMMONS: "传票",
                DocumentType.EXECUTION_RULING: "执行裁定书",
                DocumentType.OTHER: "法院文书",
            }
            title = type_titles.get(document_type, "法院文书")

            renamer = DocumentRenamer()
            new_filename = renamer.generate_filename(title=title, case_name=case_name, received_date=date.today())

            original_ext = original_path.ext.lower()
            new_ext = Path(new_filename).ext.lower()
            if original_ext != new_ext:
                new_filename = Path(new_filename).stem + original_ext

            new_path = original_path.parent / new_filename
            counter = 1
            while new_path.exists():
                stem = Path(new_filename).stem
                new_path = original_path.parent / f"{stem}_{counter}{original_ext}"
                counter += 1
                if counter > 100:
                    break

            original_path.rename(new_path)
            logger.info("文书重命名成功", extra={})
            return str(new_path)
        except Exception:
            logger.warning("文书重命名失败,保留原文件名", extra={})
            return file_path
