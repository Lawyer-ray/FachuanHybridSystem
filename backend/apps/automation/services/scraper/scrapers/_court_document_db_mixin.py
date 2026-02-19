"""法院文书爬虫 — 数据库保存 Mixin"""

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.core.interfaces import ICourtDocumentService

logger = logging.getLogger("apps.automation")


class CourtDocumentDbMixin:
    """文书数据库保存相关方法"""

    document_service: "ICourtDocumentService"

    # 子类提供
    @property
    def task(self) -> Any: ...  # type: ignore[misc]

    def _save_document_to_db(
        self,
        document_data: dict[str, Any],
        download_result: tuple[bool, str | None, str | None],
    ) -> int | None:
        """保存单个文书记录到数据库，失败时返回 None"""
        try:
            success, filepath, error = download_result
            document = self.document_service.create_document_from_api_data(
                scraper_task_id=self.task.id,
                api_data=document_data,
                case_id=self.task.case_id,
            )
            if success:
                file_size = None
                if filepath:
                    try:
                        file_size = Path(filepath).stat().st_size
                    except Exception as e:
                        logger.warning(f"无法获取文件大小: {e}")
                document = self.document_service.update_download_status(
                    document_id=document.id, status="success",
                    local_file_path=filepath, file_size=file_size,
                )
            else:
                document = self.document_service.update_download_status(
                    document_id=document.id, status="failed", error_message=error,
                )
            logger.info(
                "文书记录已保存到数据库",
                extra={
                    "operation_type": "save_document_to_db",
                    "timestamp": time.time(),
                    "document_id": document.id,
                    "c_wsmc": document.c_wsmc,
                    "download_status": document.download_status,
                    "file_path": filepath,
                },
            )
            return document.id  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(
                f"保存文书记录到数据库失败: {e}",
                extra={
                    "operation_type": "save_document_to_db_error",
                    "timestamp": time.time(),
                    "document_data": document_data,
                    "download_result": download_result,
                    "error": str(e),
                },
                exc_info=True,
            )
            return None

    def _save_documents_batch(
        self,
        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]],
    ) -> dict[str, Any]:
        """批量保存文书记录到数据库"""
        start_time = time.time()
        total = len(documents_with_results)
        success_count = 0
        failed_count = 0
        document_ids: list[int] = []

        logger.info(
            "开始批量保存文书记录",
            extra={"operation_type": "save_documents_batch_start", "timestamp": time.time(), "total_count": total},
        )
        for document_data, download_result in documents_with_results:
            document_id = self._save_document_to_db(document_data, download_result)
            if document_id is not None:
                success_count += 1
                document_ids.append(document_id)
            else:
                failed_count += 1

        elapsed_time = (time.time() - start_time) * 1000
        logger.info(
            "批量保存文书记录完成",
            extra={
                "operation_type": "save_documents_batch_complete",
                "timestamp": time.time(),
                "total_count": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "elapsed_time_ms": elapsed_time,
            },
        )
        return {"total": total, "success": success_count, "failed": failed_count, "document_ids": document_ids}
