"""Business logic services."""

from __future__ import annotations

"""
附件查询服务

负责文书路径获取、查找等只读操作.
从 DocumentAttachmentService 中拆分出来.
"""


import glob
import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS

logger = logging.getLogger("apps.automation")


class AttachmentQueryService:
    """附件查询服务 - 处理文书路径获取和查找"""

    def get_paths_for_renaming(self, sms: CourtSMS) -> list[str]:
        """获取待重命名的文书路径列表"""
        try:
            if not sms.scraper_task:
                logger.info("短信 %s 无下载任务,返回空路径列表", sms.pk)
                return []

            # 方式1:从 CourtDocument 记录获取(优先)
            paths = self._collect_from_court_documents(sms.scraper_task, set())

            # 方式2:降级从任务结果获取
            if not paths:
                paths = self._collect_from_result_files(sms.scraper_task.result, set())

            logger.info("获取到 %d 个待重命名的文书路径", len(paths))
            return paths
        except Exception as e:
            logger.warning("获取文书路径失败: %s", e)
            return []

    def get_paths_for_notification(self, sms: CourtSMS) -> list[str]:
        """获取待发送通知的文书路径列表(已去重)"""
        try:
            if not sms.scraper_task:
                logger.info("短信 %s 无下载任务,返回空路径列表", sms.pk)
                return []

            seen_paths: set[str] = set()

            # 优先从 renamed_files 获取
            result = sms.scraper_task.result
            paths = self._collect_from_renamed_files(result, seen_paths)
            if paths:
                logger.info("从 renamed_files 获取到 %d 个文书路径", len(paths))
                return paths

            # 从 CourtDocument 记录获取
            paths = self._collect_from_court_documents(sms.scraper_task, seen_paths)

            # 从原始 files 列表获取
            if not paths:
                paths = self._collect_from_result_files(result, seen_paths)

            logger.info("获取到 %d 个待发送通知的文书路径(已去重)", len(paths))
            return paths
        except Exception as e:
            logger.warning("获取通知文书路径失败: %s", e)
            return []

    def collect_existing_paths(self, file_paths: Any, seen_paths: set[str]) -> list[str]:
        """从路径列表中收集存在的文件路径(去重)"""
        collected: list[str] = []
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                abs_path = os.path.abspath(file_path)
                if abs_path not in seen_paths:
                    collected.append(file_path)
                    seen_paths.add(abs_path)
        return collected

    def _collect_from_renamed_files(self, result: Any, seen_paths: set[str]) -> list[str]:
        """从任务结果的 renamed_files 收集路径"""
        if not result or not isinstance(result, dict):
            return []
        renamed_files = result.get("renamed_files", [])
        return self.collect_existing_paths(renamed_files, seen_paths)

    def _collect_from_court_documents(self, scraper_task: Any, seen_paths: set[str]) -> list[str]:
        """从 CourtDocument 记录收集路径"""
        if not hasattr(scraper_task, "documents"):
            return []
        scraper_task.documents.filter(download_status="success")
        paths: list[Any] = []
        return self.collect_existing_paths(paths, seen_paths)

    def _collect_from_result_files(self, result: Any, seen_paths: set[str]) -> list[str]:
        """从任务结果的 files 列表收集路径"""
        if not result or not isinstance(result, dict):
            return []
        files = result.get("files", [])
        return self.collect_existing_paths(files, seen_paths)

    def find_renamed_file(self, original_path: str, sms: CourtSMS) -> str | None:
        """
        查找重命名后的文件

        当原始文件路径不存在时,尝试在同目录下查找重命名后的文件

        Args:
            original_path: 原始文件路径
            sms: CourtSMS 实例

        Returns:
            重命名后的文件路径,如果找不到则返回 None
        """
        try:
            if not original_path:
                return None

            directory = os.path.dirname(original_path)
            if not os.path.exists(directory):
                return None

            case_name: str | None = sms.case.name if sms.case else None
            if not case_name:
                return None

            pattern = os.path.join(directory, f"*{case_name[:10]}*.pdf")
            matches = glob.glob(pattern)

            if matches:
                matches.sort(key=os.path.getmtime, reverse=True)
                logger.info("找到重命名后的文件: %s", matches[0])
                return matches[0]

            return None

        except Exception as e:
            logger.warning("查找重命名文件失败: %s", e)
            return None
