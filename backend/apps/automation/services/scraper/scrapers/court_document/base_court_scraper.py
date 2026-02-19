"""
法院文书下载爬虫基类

提供通用的调试、文件管理和数据库保存功能
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings

from apps.automation.services.scraper.scrapers.base import BaseScraper

if TYPE_CHECKING:
    from apps.core.interfaces import ICourtDocumentService

logger = logging.getLogger("apps.automation")

# 调试模式配置(从 Django settings 读取)
DEBUG_MODE = getattr(settings, "DEBUG", False)  # 跟随 Django DEBUG 设置
PAUSE_ON_ERROR = False  # 设置为 True 在错误时暂停(需要手动继续)


class BaseCourtDocumentScraper(BaseScraper):
    """
    法院文书下载爬虫基类

    提供通用功能:
    - 调试日志和页面状态保存
    - 文书服务依赖注入
    - 下载目录准备
    - 数据库保存
    """

    def __init__(self, task: Any, document_service: ICourtDocumentService | None = None) -> None:
        super().__init__(task)
        self.site_name = "court_document"
        self.debug_info: dict[str, Any] = {}  # 存储调试信息
        self._document_service = document_service  # 文书服务(通过依赖注入)

    @property
    def document_service(self) -> ICourtDocumentService:
        """
        获取文书服务实例

        使用延迟获取模式,支持依赖注入和默认实现
        """
        if self._document_service is None:
            from apps.core.interfaces import ServiceLocator

            self._document_service = ServiceLocator.get_court_document_service()
        return self._document_service

    def _debug_log(self, message: str, data: Any | None = None) -> None:
        """调试日志"""
        if DEBUG_MODE:
            logger.info(f"[DEBUG] {message}")
            if data:
                logger.info(f"[DEBUG] Data: {data}")

    def _save_debug_info(self, key: str, value: Any) -> None:
        """保存调试信息"""
        self.debug_info[key] = value
        if DEBUG_MODE:
            logger.info(f"[DEBUG] Saved {key}: {type(value)}")

    def _analyze_page_elements(self) -> dict[str, Any]:
        """
        分析页面元素,用于调试

        Returns:
            页面元素分析结果
        """
        analysis: dict[str, Any] = {
            "url": self.page.url,
            "title": self.page.title(),
            "buttons": [],
            "links": [],
            "download_elements": [],
            "iframes": [],
        }

        try:
            # 分析按钮
            buttons = self.page.locator("button").all()
            for i, btn in enumerate(buttons[:10]):
                try:
                    analysis["buttons"].append(
                        {
                            "index": i,
                            "text": btn.inner_text()[:50] if btn.inner_text() else "",
                            "visible": btn.is_visible(),
                        }
                    )
                except Exception:
                    logger.exception("操作失败")

                    pass

            # 分析链接
            links = self.page.locator("a").all()
            for i, link in enumerate(links[:10]):
                try:
                    analysis["links"].append(
                        {
                            "index": i,
                            "text": link.inner_text()[:50] if link.inner_text() else "",
                            "href": link.get_attribute("href")[:100] if link.get_attribute("href") else "",
                            "visible": link.is_visible(),
                        }
                    )
                except Exception:
                    logger.exception("操作失败")

                    pass

            # 分析包含"下载"的元素
            download_elements = self.page.locator('*:has-text("下载")').all()
            for i, elem in enumerate(download_elements[:10]):
                try:
                    tag = elem.evaluate("el => el.tagName")
                    analysis["download_elements"].append(
                        {
                            "index": i,
                            "tag": tag,
                            "text": elem.inner_text()[:50] if elem.inner_text() else "",
                            "visible": elem.is_visible(),
                        }
                    )
                except Exception:
                    logger.exception("操作失败")

                    pass

            # 分析 iframe
            iframes = self.page.locator("iframe").all()
            for i, iframe in enumerate(iframes):
                try:
                    analysis["iframes"].append(
                        {
                            "index": i,
                            "src": iframe.get_attribute("src")[:100] if iframe.get_attribute("src") else "",
                        }
                    )
                except Exception:
                    logger.exception("操作失败")

                    pass

        except Exception as e:
            logger.exception("操作失败")
            analysis["error"] = str(e)

        return analysis

    def _save_page_state(self, name: str) -> dict[str, Any]:
        """
        保存页面状态(截图 + HTML + 元素分析)

        Args:
            name: 状态名称

        Returns:
            保存的文件路径字典
        """
        download_dir = self._prepare_download_dir()

        # 保存截图
        screenshot_path = self.screenshot(name)

        # 保存 HTML
        html_path = download_dir / f"{name}_page.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.page.content())

        # 保存元素分析
        analysis = self._analyze_page_elements()
        analysis_path = download_dir / f"{name}_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)

        logger.info(f"[DEBUG] 页面状态已保存: {name}")
        logger.info(f"  - 截图: {screenshot_path}")
        logger.info(f"  - HTML: {html_path}")
        logger.info(f"  - 分析: {analysis_path}")

        # 打印关键信息
        logger.info(f"  - URL: {analysis['url']}")
        logger.info(f"  - 标题: {analysis['title']}")
        logger.info(f"  - 按钮数: {len(analysis['buttons'])}")
        logger.info(f"  - 链接数: {len(analysis['links'])}")
        logger.info(f"  - 下载元素数: {len(analysis['download_elements'])}")
        logger.info(f"  - iframe数: {len(analysis['iframes'])}")

        return {
            "screenshot": screenshot_path,
            "html": str(html_path),
            "analysis": analysis,
        }

    def _prepare_download_dir(self) -> Path:
        """
        准备下载目录

        Returns:
            下载目录路径
        """
        # 如果任务关联了案件,使用案件 ID 作为目录名
        if self.cast(int, self.task.case_id):
            download_dir = (
                Path(settings.MEDIA_ROOT)
                / "case_logs"
                / str(cast(int, self.cast(int, self.task.case_id)))
                / "documents"
            )
        else:
            download_dir = Path(settings.MEDIA_ROOT) / "automation" / "downloads" / f"task_{self.task.id}"

        download_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"下载目录: {download_dir}")

        return download_dir

    def _save_document_to_db(
        self, document_data: dict[str, Any], download_result: tuple[bool, str | None, str | None]
    ) -> int | None:
        """
        保存单个文书记录到数据库

        此方法不会抛出异常,所有错误都会被捕获并记录,
        确保数据库保存失败不会阻断下载流程.

        Args:
            document_data: 文书数据字典,包含 API 返回的所有字段
            download_result: 下载结果元组 (成功标志, 文件路径, 错误信息)

        Returns:
            创建的文书记录 ID,失败时返回 None

        Raises:
            无异常抛出,所有错误通过日志记录
        """
        try:
            success, filepath, error = download_result

            # 先创建文书记录
            task_id_value = cast(int, self.task.id)
            task_case_id = cast(int | None, self.task.case_id) if self.task.case else None
            document = self.document_service.create_document_from_api_data(
                scraper_task_id=task_id_value, api_data=document_data, case_id=task_case_id
            )

            # 根据下载结果更新状态
            if success:
                # 获取文件大小
                file_size = None
                if filepath:
                    try:
                        file_size = Path(filepath).stat().st_size
                    except Exception as e:
                        logger.warning(f"无法获取文件大小: {e}")

                # 更新为成功状态
                document = self.document_service.update_download_status(
                    document_id=cast(int, document.id), status="success", local_file_path=filepath, file_size=file_size
                )
            else:
                # 更新为失败状态
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
            # 捕获所有异常,记录详细日志,但不抛出
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
        self, documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]]
    ) -> dict[str, Any]:
        """
        批量保存文书记录到数据库

        使用批量创建优化性能,同时确保单个失败不影响其他记录.

        Args:
            documents_with_results: 文书数据和下载结果的列表
                每个元素是 (document_data, download_result) 元组

        Returns:
            保存结果统计字典,包含:
            - total: 总数
            - success: 成功保存的数量
            - failed: 失败的数量
            - document_ids: 成功保存的文书 ID 列表

        Raises:
            无异常抛出,所有错误通过日志记录
        """
        start_time = time.time()
        total = len(documents_with_results)
        success_count = 0
        failed_count = 0
        document_ids: list[int] = []

        logger.info(
            "开始批量保存文书记录",
            extra={"operation_type": "save_documents_batch_start", "timestamp": time.time(), "total_count": total},
        )

        # 逐个保存(确保错误隔离)
        for document_data, download_result in documents_with_results:
            document_id = self._save_document_to_db(document_data, download_result)

            if document_id is not None:
                success_count += 1
                document_ids.append(document_id)
            else:
                failed_count += 1

        elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒

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
