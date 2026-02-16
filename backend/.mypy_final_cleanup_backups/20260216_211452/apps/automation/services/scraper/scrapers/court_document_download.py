"""
法院文书下载相关方法

负责文书下载、保存等功能.
"""

import logging
import time
from typing import TYPE_CHECKING, Any, Protocol, cast

from apps.core.config import get_config
from apps.core.path import Path

from .court_document_download_gdems import CourtDocumentGdemsDownloadMixin
from .court_document_download_jysd import CourtDocumentJysdDownloadMixin
from .court_document_download_zxfw import CourtDocumentZxfwDownloadMixin

if TYPE_CHECKING:
    from apps.automation.models import ScraperTask
    from apps.core.interfaces import ICourtDocumentService

    class _DownloadHost(Protocol):
        task: ScraperTask

        @property
        def document_service(self) -> ICourtDocumentService: ...


logger = logging.getLogger("apps.automation")


class CourtDocumentDownloadMixin(
    CourtDocumentZxfwDownloadMixin,
    CourtDocumentJysdDownloadMixin,
    CourtDocumentGdemsDownloadMixin,
):
    @property
    def _logger(self) -> logging.Logger:
        from .court_document.base_court_scraper import logger as court_logger

        return court_logger

    def _prepare_download_dir(self: "_DownloadHost") -> Any:
        """
        准备下载目录

        Returns:
            下载目录路径
        """
        media_root = get_config("django.media_root", None)
        if not media_root:
            raise RuntimeError("django.media_root 未配置")
        media_root_path = Path(str(media_root))

        if self.cast(int | None, self.cast(int, task.case_id)):
            download_dir = (
                media_root_path / "case_logs" / str(self.cast(int | None, self.cast(int, task.case_id))) / "documents"
            )
        else:
            download_dir = media_root_path / "automation" / "downloads" / f"task_{cast(int, self.task.pk)}"

        download_dir.makedirs_p()
        logger.info(f"下载目录: {download_dir}")

        return download_dir

    def _save_document_to_db(
        self: "_DownloadHost", document_data: dict[str, Any], download_result: tuple[bool, str | None, str | None]
    ) -> int | None:
        """
        保存单个文书记录到数据库

        Args:
            document_data: 文书数据字典
            download_result: 下载结果元组

        Returns:
            创建的文书记录 ID,失败时返回 None
        """
        try:
            success, filepath, error = download_result

            document = self.document_service.create_document_from_api_data(
                scraper_task_id=cast(int, self.cast(int, task.pk)),
                api_data=document_data,
                case_id=self.cast(int | None, self.cast(int, task.case_id)),
            )

            if success:
                file_size: Any | None = None
                relative_path = None
                if filepath:
                    try:
                        file_size = Path(filepath).stat().st_size
                        # 转换为相对于 MEDIA_ROOT 的相对路径
                        media_root = get_config("django.media_root", None)
                        if media_root:
                            media_root_path = Path(str(media_root))
                            relative_path = str(Path(filepath).relative_to(media_root_path))
                        else:
                            relative_path = filepath
                    except Exception as e:
                        logger.warning(f"无法获取文件信息: {e}")
                        relative_path = filepath

                document = self.document_service.update_download_status(
                    document_id=cast(int, document.id),
                    status="success",
                    local_file_path=relative_path,
                    file_size=file_size,
                )
            else:
                document = self.document_service.update_download_status(
                    document_id=cast(int, document.id), status="failed", error_message=error
                )

            logger.info(
                "文书记录已保存到数据库",
                extra={
                    "operation_type": "save_document_to_db",
                    "timestamp": time.time(),
                    "document_id": cast(int, document.id),
                    "c_wsmc": document.c_wsmc,
                    "download_status": document.download_status,
                    "file_path": filepath,
                },
            )

            return cast(int, document.id)

        except Exception as e:
            logger.error(f"保存文书记录到数据库失败: {e}", exc_info=True)
            return None

    def _save_documents_batch(
        self, documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]]
    ) -> dict[str, Any]:
        """
        批量保存文书记录到数据库

        Args:
            documents_with_results: 文书数据和下载结果的列表

        Returns:
            保存结果统计字典
        """
        start_time = time.time()
        total = len(documents_with_results)
        success_count = 0
        failed_count = 0
        document_ids: list[int] = []

        logger.info(f"开始批量保存文书记录,共 {total} 条")

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
