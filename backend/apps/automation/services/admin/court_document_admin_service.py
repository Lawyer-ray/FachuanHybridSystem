"""
法院文书 Admin Service
负责处理法院文书的复杂管理逻辑
"""

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q, QuerySet, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone

from apps.automation.models import CourtDocument, CourtSMS, DocumentDownloadStatus, ScraperTask
from apps.core.exceptions import BusinessException, NotFoundError, ValidationException
from apps.core.services.storage_service import resolve_media_path


def _add_protected_path(protected_paths: set[str], raw_path: Any) -> None:
    """把一个 DB 里的文件路径归一成规范绝对路径后并入白名单（解析不了就忽略）。"""
    if not raw_path:
        return
    try:
        protected_paths.add(resolve_media_path(str(raw_path)).resolve().as_posix())
    except (OSError, ValueError):
        return


class CourtDocumentAdminService:
    """
    法院文书管理服务

    负责处理Admin层的复杂业务逻辑：
    - 批量下载文书
    - 批量删除文书
    - 文书统计分析
    - 文件管理操作
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    @transaction.atomic
    def batch_download_documents(self, document_ids: list[int]) -> dict[str, Any]:
        """
        批量下载文书（暂未接入下载消费者）

        全仓无批量下载消费者：若在此处置为 DOWNLOADING，文书将永久卡死。
        因此只做校验并直接返回明确错误，不修改任何状态。

        Args:
            document_ids: 文书ID列表

        Returns:
            Dict[str, Any]: 下载结果统计（当前实现不会返回）

        Raises:
            ValidationException: 参数验证失败 / 批量下载暂未接入
        """
        if not document_ids:
            raise ValidationException(message="没有选中任何文书", code="NO_DOCUMENTS_SELECTED", errors={})

        raise ValidationException(
            message="批量下载暂未接入，请在法院短信详情中逐个下载",
            code="BATCH_DOWNLOAD_NOT_IMPLEMENTED",
            errors={},
        )

    @transaction.atomic
    def batch_delete_documents(
        self, document_ids: list[int], delete_files: bool = False
    ) -> dict[str, Any]:  # pragma: no cover
        """
        批量删除文书记录

        Args:
            document_ids: 文书ID列表
            delete_files: 是否同时删除本地文件

        Returns:
            Dict[str, Any]: 删除结果统计

        Raises:
            ValidationException: 参数验证失败
            BusinessException: 删除失败
        """
        if not document_ids:
            raise ValidationException(message="没有选中任何文书", code="NO_DOCUMENTS_SELECTED", errors={})

        try:
            # 获取要删除的文书
            documents = CourtDocument.objects.filter(id__in=document_ids)

            if not documents.exists():
                raise ValidationException(
                    message="没有找到要删除的文书", code="NO_DOCUMENTS_FOUND", errors={"document_ids": document_ids}
                )

            deleted_files_count = 0
            file_errors = []

            # 如果需要删除文件（local_file_path 可能是 media 相对路径，删除前先解析）
            if delete_files:
                for document in documents:
                    if not document.local_file_path:
                        continue
                    file_path = resolve_media_path(document.local_file_path)
                    if file_path.exists():
                        try:
                            file_path.unlink()
                            deleted_files_count += 1
                        except Exception as e:
                            file_errors.append(
                                {"document_id": document.id, "file_path": document.local_file_path, "error": str(e)}
                            )

            # 删除数据库记录
            deleted_count = documents.count()
            documents.delete()

            result = {
                "deleted_records": deleted_count,
                "deleted_files": deleted_files_count,
                "file_errors": file_errors,
            }

            self.logger.info(
                "批量删除文书完成",
                extra={"action": "batch_delete_documents", "result": result, "delete_files": delete_files},
            )

            return result

        except Exception as e:
            self.logger.exception(
                "批量删除文书失败",
                extra={
                    "action": "batch_delete_documents",
                    "document_ids": document_ids,
                    "delete_files": delete_files,
                    "error": str(e),
                },
            )
            raise BusinessException(
                message="批量删除文书失败", code="BATCH_DELETE_FAILED", errors={"error": str(e)}
            ) from e

    def get_document_statistics(self, queryset: QuerySet[Any, Any] | None = None) -> dict[str, Any]:  # pragma: no cover
        """
        获取文书统计数据

        Args:
            queryset: 可选的查询集，如果不提供则统计所有文书

        Returns:
            Dict[str, Any]: 统计数据

        Raises:
            BusinessException: 统计失败
        """
        try:
            if queryset is None:
                queryset = CourtDocument.objects.all()

            # 基础统计
            total_documents = queryset.count()

            # 按状态统计 — 一次 aggregate 条件计数，替代逐状态 .count() 查询
            status_counts: dict[str, Any] = queryset.aggregate(
                **{
                    f"status_{code}": Count("id", filter=Q(download_status=code))
                    for code, _label in DocumentDownloadStatus.choices
                }
            )
            status_stats = {}
            for status_code, status_name in DocumentDownloadStatus.choices:
                count = status_counts[f"status_{status_code}"]
                status_stats[status_code] = {
                    "name": status_name,
                    "count": count,
                    "percentage": (count / total_documents * 100) if total_documents > 0 else 0,
                }

            # 按法院统计
            court_stats = list(
                queryset.values("c_fymc")
                .annotate(
                    total=Count("id"),
                    success=Count("id", filter=Q(download_status=DocumentDownloadStatus.SUCCESS)),
                    pending=Count("id", filter=Q(download_status=DocumentDownloadStatus.PENDING)),
                    failed=Count("id", filter=Q(download_status=DocumentDownloadStatus.FAILED)),
                )
                .order_by("-total")[:20]
            )  # 只显示前20个法院

            # 按文件格式统计
            format_stats = list(queryset.values("c_wjgs").annotate(count=Count("id")).order_by("-count"))

            # 文件大小统计
            file_size_stats = queryset.filter(
                download_status=DocumentDownloadStatus.SUCCESS, file_size__isnull=False
            ).aggregate(total_size=Sum("file_size"), avg_size=Avg("file_size"), count=Count("id"))

            # 按日期统计（最近30天）— 单条 TruncDate 查询替代 60 条逐日查询
            from datetime import timedelta
            from zoneinfo import ZoneInfo

            now = timezone.now()
            thirty_days_ago = now - timedelta(days=30)
            # M2 修复：TruncDate 需要显式指定 tzinfo，否则按 UTC 截断导致凌晨记录归到前一天
            app_tz = ZoneInfo(settings.TIME_ZONE)
            date_stats_raw = (
                queryset.filter(created_at__gte=thirty_days_ago)
                .annotate(date=TruncDate("created_at", tzinfo=app_tz))
                .values("date")
                .annotate(
                    total=Count("id"),
                    success=Count("id", filter=Q(download_status=DocumentDownloadStatus.SUCCESS)),
                )
                .order_by("date")
            )
            # 构建 {date: {total, success}} 映射，再补齐缺失日期
            date_map: dict[Any, dict[str, int]] = {}
            for row in date_stats_raw:
                date_map[row["date"]] = {"total": row["total"], "success": row["success"]}

            date_stats = []
            for i in range(30):
                date = (now - timedelta(days=i)).date()
                counts = date_map.get(date, {"total": 0, "success": 0})
                date_stats.append(
                    {"date": date.strftime("%m-%d"), "total": counts["total"], "success": counts["success"]}
                )
            date_stats.reverse()  # 按时间正序

            # 按爬虫任务统计
            task_stats = list(
                queryset.values("scraper_task__id", "scraper_task__task_type")
                .annotate(
                    count=Count("id"), success=Count("id", filter=Q(download_status=DocumentDownloadStatus.SUCCESS))
                )
                .order_by("-count")[:10]
            )  # 只显示前10个任务

            result = {
                "total_documents": total_documents,
                "status_stats": status_stats,
                "court_stats": court_stats,
                "format_stats": format_stats,
                "file_size_stats": file_size_stats,
                "date_stats": date_stats,
                "task_stats": task_stats,
            }

            self.logger.info(
                "获取文书统计数据完成", extra={"action": "get_document_statistics", "total_documents": total_documents}
            )

            return result

        except Exception as e:
            self.logger.exception("获取文书统计数据失败", extra={"action": "get_document_statistics", "error": str(e)})
            raise BusinessException(
                message="获取文书统计数据失败", code="GET_DOCUMENT_STATS_FAILED", errors={"error": str(e)}
            ) from e

    @transaction.atomic
    def retry_failed_downloads(self, document_ids: list[int] | None = None) -> dict[str, Any]:
        """
        重试失败的下载任务

        Args:
            document_ids: 可选的文书ID列表，如果不提供则重试所有失败的下载

        Returns:
            Dict[str, Any]: 重试结果

        Raises:
            BusinessException: 重试失败
        """
        try:
            # 构建查询条件
            query = Q(download_status=DocumentDownloadStatus.FAILED)
            if document_ids:
                query &= Q(id__in=document_ids)

            failed_documents = CourtDocument.objects.filter(query)

            if not failed_documents.exists():
                return {"retried_count": 0, "message": "没有找到失败的下载任务"}

            # 重置状态为待下载
            retried_count = failed_documents.update(
                download_status=DocumentDownloadStatus.PENDING, error_message="", updated_at=timezone.now()
            )

            result = {"retried_count": retried_count, "message": f"已重置 {retried_count} 个失败的下载任务"}

            self.logger.info(
                "重试失败下载任务完成",
                extra={
                    "action": "retry_failed_downloads",
                    "retried_count": retried_count,
                    "document_ids": document_ids,
                },
            )

            return result

        except Exception as e:
            self.logger.exception(
                "重试失败下载任务失败",
                extra={"action": "retry_failed_downloads", "document_ids": document_ids, "error": str(e)},
            )
            raise BusinessException(
                message="重试失败下载任务失败", code="RETRY_FAILED_DOWNLOADS_FAILED", errors={"error": str(e)}
            ) from e

    def cleanup_orphaned_files(
        self,
        *,
        dry_run: bool = True,
        min_age_hours: float = 24.0,
    ) -> dict[str, Any]:  # pragma: no cover
        """
        清理孤立文件（数据库里没有任何引用、且落盘已足够久的文件）

        数据安全默认值（审计 P05-01：旧实现会立刻物理删除，且白名单只认
        `status=success` 且路径字符串逐字相等，导致在飞任务的文件、被短信/案件日志
        引用的副本、以及「库里存绝对路径」的存量文件全被判成孤儿）：

        - ``dry_run=True``：默认**只返回将被删除的清单**，不落删除；
        - ``min_age_hours=24``：太新的文件可能正在下载/归档途中，跳过；
        - 白名单见 :meth:`_collect_protected_file_paths`；
        - 两侧路径都 ``Path.resolve()`` 后比较（绝对路径 / 相对路径统一）；
        - 真正删除前用 ``logger.warning`` 打出完整清单，删文件不可恢复，事后只能靠这条日志定位。

        Args:
            dry_run: True（默认）只列清单不删除
            min_age_hours: 只处理 mtime 早于 N 小时的文件

        Returns:
            Dict[str, Any]: orphaned_files（数量）/ orphaned_paths（清单）/
            deleted_files / delete_errors / dry_run

        Raises:
            BusinessException: 清理失败
        """
        try:
            media_root_setting = str(getattr(settings, "MEDIA_ROOT", "") or "").strip()
            if not media_root_setting:
                return {
                    "orphaned_files": 0,
                    "orphaned_paths": [],
                    "deleted_files": 0,
                    "delete_errors": [],
                    "dry_run": dry_run,
                    "message": "MEDIA_ROOT 未配置",
                }

            documents_dir = Path(media_root_setting) / "court_documents"

            if not documents_dir.exists():
                return {
                    "orphaned_files": 0,
                    "orphaned_paths": [],
                    "deleted_files": 0,
                    "delete_errors": [],
                    "dry_run": dry_run,
                    "message": "文档目录不存在",
                }

            protected_paths = self._collect_protected_file_paths()
            cutoff_timestamp = timezone.now().timestamp() - min_age_hours * 3600

            orphaned_files: list[str] = []
            for file_path in sorted(documents_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                try:
                    if file_path.stat().st_mtime > cutoff_timestamp:
                        continue
                except OSError:
                    continue
                resolved_path = file_path.resolve().as_posix()
                if resolved_path in protected_paths:
                    continue
                orphaned_files.append(resolved_path)

            result: dict[str, Any] = {
                "orphaned_files": len(orphaned_files),
                "orphaned_paths": orphaned_files,
                "deleted_files": 0,
                "delete_errors": [],
                "dry_run": dry_run,
            }

            if not orphaned_files or dry_run:
                self.logger.info("清理孤立文件完成", extra={"action": "cleanup_orphaned_files", "result": result})
                return result

            # 删除前把完整清单写进日志（不可恢复操作的追溯依据）
            self.logger.warning(
                "准备删除 %s 个孤立文书文件: %s",
                len(orphaned_files),
                orphaned_files,
                extra={"action": "cleanup_orphaned_files", "orphaned_paths": orphaned_files},
            )

            deleted_count = 0
            delete_errors: list[dict[str, str]] = []
            for file_path_str in orphaned_files:
                try:
                    Path(file_path_str).unlink()
                    deleted_count += 1
                except (OSError, ValueError) as e:
                    delete_errors.append({"file_path": file_path_str, "error": str(e)})

            result["deleted_files"] = deleted_count
            result["delete_errors"] = delete_errors

            self.logger.info("清理孤立文件完成", extra={"action": "cleanup_orphaned_files", "result": result})

            return result

        except (OSError, ValueError) as e:
            self.logger.exception("清理孤立文件失败", extra={"action": "cleanup_orphaned_files", "error": str(e)})
            raise BusinessException(
                message="清理孤立文件失败", code="CLEANUP_ORPHANED_FILES_FAILED", errors={"error": str(e)}
            ) from e

    def _collect_protected_file_paths(self) -> set[str]:
        """数据库里仍被引用的文件（规范绝对路径集合）——这些都不是孤儿。

        - ``CourtDocument.local_file_path``：**不看下载状态**。pending/downloading
          可能正在往这份文件里写，failed 也可能被 ``retry_failed_downloads`` 写回同一路径；
        - ``CourtSMS.document_file_paths``：短信详情与下载都按这份清单取文书；
        - ``CaseLogAttachment.file``：已归档到案件日志的副本，律师正在看的那份。

        两侧都经 ``resolve_media_path(...).resolve()`` 归一后再比：库里可能存 media 相对
        路径、也可能存绝对路径（历史存量），逐字比较会把同一份文件判成两个。
        """
        protected_paths: set[str] = set()

        document_paths = (
            CourtDocument.objects.exclude(local_file_path__isnull=True)
            .exclude(local_file_path="")
            .values_list("local_file_path", flat=True)
        )
        for raw_path in document_paths:
            _add_protected_path(protected_paths, raw_path)

        for raw_paths in CourtSMS.objects.values_list("document_file_paths", flat=True):
            if not isinstance(raw_paths, list):
                continue
            for raw_path in raw_paths:
                _add_protected_path(protected_paths, raw_path)

        from apps.cases.models import CaseLogAttachment

        for attachment in CaseLogAttachment.objects.all().iterator():
            file_field = getattr(attachment, "file", None)
            if not file_field:
                continue
            _add_protected_path(protected_paths, getattr(file_field, "name", ""))

        return protected_paths

    def get_download_progress(self, task_id: int | None = None) -> dict[str, Any]:  # pragma: no cover
        """
        获取下载进度统计

        Args:
            task_id: 可选的爬虫任务ID，如果提供则只统计该任务的进度

        Returns:
            Dict[str, Any]: 下载进度数据

        Raises:
            BusinessException: 获取进度失败
        """
        try:
            # 构建查询条件
            queryset = CourtDocument.objects.all()
            if task_id:
                queryset = queryset.filter(scraper_task_id=task_id)

            # 统计各状态的数量
            total = queryset.count()
            pending = queryset.filter(download_status=DocumentDownloadStatus.PENDING).count()
            downloading = queryset.filter(download_status=DocumentDownloadStatus.DOWNLOADING).count()
            success = queryset.filter(download_status=DocumentDownloadStatus.SUCCESS).count()
            failed = queryset.filter(download_status=DocumentDownloadStatus.FAILED).count()

            # 计算进度百分比
            progress_percentage = (success / total * 100) if total > 0 else 0

            result = {
                "total": total,
                "pending": pending,
                "downloading": downloading,
                "success": success,
                "failed": failed,
                "progress_percentage": progress_percentage,
                "task_id": task_id,
            }

            self.logger.info(
                "获取下载进度完成",
                extra={
                    "action": "get_download_progress",
                    "task_id": task_id,
                    "progress_percentage": progress_percentage,
                },
            )

            return result

        except Exception as e:
            self.logger.exception(
                "获取下载进度失败", extra={"action": "get_download_progress", "task_id": task_id, "error": str(e)}
            )
            raise BusinessException(
                message="获取下载进度失败", code="GET_DOWNLOAD_PROGRESS_FAILED", errors={"error": str(e)}
            ) from e
