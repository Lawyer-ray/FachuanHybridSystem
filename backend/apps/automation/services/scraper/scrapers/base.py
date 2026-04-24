"""
爬虫基类
"""

import logging
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.automation.models import ScraperTask, ScraperTaskStatus

# 所有服务通过 ServiceLocator 获取
from apps.automation.services.scraper.core.anti_detection import anti_detection

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

logger = logging.getLogger("apps.automation")


def _safe_save_task(task: ScraperTask) -> None:
    """
    安全地保存任务状态

    Args:
        task: 爬虫任务对象
    """
    try:
        from django.db import connection

        # 确保数据库连接是干净的（避免线程间共享连接的问题）
        connection.close()
        task.save()
    except Exception as e:
        logger.warning("保存任务状态时出错: %s", e, exc_info=True)


def is_playwright_available() -> bool:
    """检查 Playwright 是否已安装且可用"""
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


class BaseScraper:
    """
    爬虫基类

    所有具体的爬虫都应该继承此类并实现 _run 方法

    类属性:
        requires_browser: 是否需要浏览器环境，默认 True。
            设为 False 则 execute() 跳过浏览器创建，适用于纯 API 爬虫。
    """

    requires_browser: bool = True

    def __init__(self, task: ScraperTask):
        """
        初始化爬虫

        Args:
            task: 爬虫任务对象
        """
        self.task = task

        # 通过 ServiceLocator 获取服务
        from apps.core.interfaces import ServiceLocator

        self.browser_service = ServiceLocator.get_browser_service()
        self.captcha_service = ServiceLocator.get_captcha_service()
        self.anti_detection = anti_detection
        self.validator = ServiceLocator.get_validator_service()
        self.security = ServiceLocator.get_security_service()
        self.monitor = ServiceLocator.get_monitor_service()
        self.context: "BrowserContext | None" = None
        self.page: "Page | None" = None
        self.site_name: str | None = None  # 子类应设置网站名称

    def execute(self) -> dict[str, Any]:
        """
        执行爬虫任务

        Returns:
            执行结果字典
        """
        logger.info("开始执行任务 %s: %s", self.task.id, self.task.get_task_type_display())

        # 更新状态为执行中
        self.task.status = ScraperTaskStatus.RUNNING
        self.task.started_at = timezone.now()
        _safe_save_task(self.task)

        try:
            # 解密配置中的敏感信息
            if self.task.config:
                self.task.config = self.security.decrypt_config(self.task.config)

            if self.requires_browser:
                # 需要浏览器：创建独立的浏览器上下文（启用反检测）
                if not is_playwright_available():
                    raise RuntimeError(
                        "当前任务需要 Playwright 浏览器，但 Playwright 未安装。"
                        "请运行: uv add playwright && playwright install chromium"
                    )
                self.context = self.browser_service.create_context(use_anti_detection=True)
                assert self.context is not None
                self.page = self.context.new_page()

                # 注入反检测脚本
                self.anti_detection.inject_stealth_script(self.page)

            # 执行具体的爬虫逻辑
            result = self._run()

            # 更新为成功状态
            self.task.status = ScraperTaskStatus.SUCCESS
            self.task.result = result
            self.task.error_message = None

            logger.info("任务 %s 执行成功", self.task.id)
            return result

        except Exception as e:
            # 更新为失败状态
            self.task.status = ScraperTaskStatus.FAILED
            self.task.error_message = str(e)
            logger.error("任务 %s 执行失败: %s", self.task.id, e, exc_info=True)
            raise

        finally:
            # 清理资源
            self._cleanup()
            self.task.finished_at = timezone.now()
            _safe_save_task(self.task)

    def _run(self) -> dict[str, Any]:
        """
        具体的爬虫逻辑（子类必须实现）

        Returns:
            执行结果字典

        Raises:
            NotImplementedError: 子类未实现此方法
        """
        raise NotImplementedError("子类必须实现 _run 方法")

    def _cleanup(self) -> None:
        """清理资源"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            logger.info("任务 %s 资源已清理", self.task.id)
        except Exception as e:
            logger.warning("清理资源时出错: %s", e)

    def navigate_to_url(self, timeout: int = 30000) -> None:
        """
        导航到任务指定的 URL

        Args:
            timeout: 超时时间（毫秒）
        """
        assert self.page is not None, "浏览器页面未初始化，请先调用 execute()"
        logger.info("导航到: %s", self.task.url)
        self.page.goto(self.task.url, timeout=timeout, wait_until="domcontentloaded")

    def wait_for_selector(self, selector: str, timeout: int = 10000) -> None:
        """
        等待元素出现

        Args:
            selector: CSS 选择器
            timeout: 超时时间（毫秒）
        """
        assert self.page is not None, "浏览器页面未初始化，请先调用 execute()"
        logger.debug("等待元素: %s", selector)
        self.page.wait_for_selector(selector, timeout=timeout)

    def screenshot(self, name: str = "screenshot") -> str:
        """
        截图（用于调试）

        Args:
            name: 截图文件名

        Returns:
            截图文件路径
        """
        from pathlib import Path

        from django.conf import settings

        screenshot_dir = Path(settings.MEDIA_ROOT) / "automation" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{name}_{self.task.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = screenshot_dir / filename

        assert self.page is not None, "浏览器页面未初始化，请先调用 execute()"
        self.page.screenshot(path=str(filepath))
        logger.info("截图已保存: %s", filepath)

        return str(filepath)

    def validate_and_clean_text(self, text: str) -> str:
        """校验并清洗文本"""
        return self.validator.clean_text(text)
