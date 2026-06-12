"""
验证码识别器接口

提供可插拔的验证码识别功能，支持多种识别服务。
"""

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger("apps.automation")


class CaptchaRecognizer(ABC):
    """
    验证码识别器抽象接口

    定义验证码识别的标准接口，允许不同的识别服务实现。
    所有实现必须提供两个核心方法：
    1. recognize() - 从字节流识别验证码
    2. recognize_from_element() - 从页面元素识别验证码

    实现者应该：
    - 在识别失败时返回 None 而不是抛出异常
    - 记录详细的错误日志以便调试
    - 处理所有可能的异常情况
    """

    @abstractmethod
    def recognize(self, image_bytes: bytes) -> str | None:
        """
        从图片字节流识别验证码

        Args:
            image_bytes: 图片的字节数据

        Returns:
            识别出的验证码文本，识别失败返回 None

        Note:
            - 实现应该处理所有异常并返回 None
            - 不应该抛出异常到调用者
            - 应该记录错误日志以便调试
        """
        pass

    @abstractmethod
    def recognize_from_element(self, page: Any, selector: str) -> str | None:
        """
        从页面元素识别验证码

        Args:
            page: Playwright Page 对象
            selector: 验证码图片元素的 CSS 选择器

        Returns:
            识别出的验证码文本，识别失败返回 None

        Note:
            - 实现应该处理元素定位失败、截图失败等异常
            - 不应该抛出异常到调用者
            - 应该记录错误日志以便调试
        """
        pass


class DdddocrRecognizer(CaptchaRecognizer):
    """
    使用 ddddocr 库实现的验证码识别器

    ddddocr 是一个开源的 OCR 库，专门用于识别验证码。
    这个实现提供了基本的验证码识别功能，适用于大多数简单验证码。

    Attributes:
        ocr: ddddocr.DdddOcr 实例，用于执行实际的识别工作

    Example:
        >>> recognizer = DdddocrRecognizer()
        >>> with open('captcha.png', 'rb') as f:
        ...     image_bytes = f.read()
        >>> result = recognizer.recognize(image_bytes)
        >>> logger.info(result)  # '1234'
    """

    def __init__(self, show_ad: bool = False):  # pragma: no cover
        """
        初始化 ddddocr 识别器

        Args:
            show_ad: 是否显示 ddddocr 的广告信息，默认 False

        Raises:
            ImportError: 如果 ddddocr 库未安装
        """
        try:
            import ddddocr

            self.ocr = ddddocr.DdddOcr(show_ad=show_ad)
            logger.info("✅ DdddocrRecognizer 初始化成功")
        except ImportError as e:
            logger.error("❌ ddddocr 未安装，请运行: uv add ddddocr")
            raise ImportError("ddddocr 库未安装。请运行: uv add ddddocr") from e

    def recognize(self, image_bytes: bytes) -> str | None:  # pragma: no cover
        """
        从图片字节流识别验证码

        Args:
            image_bytes: 图片的字节数据

        Returns:
            识别出的验证码文本（已去除空格），识别失败返回 None
        """
        if not image_bytes:
            logger.warning("⚠️ 图片字节流为空")
            return None

        try:
            result = self.ocr.classification(image_bytes)
            # 清理结果：去除空格
            cleaned_result = result.strip().replace(" ", "")
            logger.info(f"✅ 验证码识别成功: {cleaned_result}")
            return cast(str | None, cleaned_result)
        except Exception as e:
            logger.error(f"❌ 验证码识别失败: {e}", exc_info=True)
            return None

    def recognize_from_element(self, page: Any, selector: str) -> str | None:  # pragma: no cover
        """
        从页面元素识别验证码

        Args:
            page: Playwright Page 对象
            selector: 验证码图片元素的 CSS 选择器

        Returns:
            识别出的验证码文本，识别失败返回 None
        """
        try:
            # 定位元素
            element = page.locator(selector)

            # 等待元素可见
            element.wait_for(state="visible", timeout=5000)

            # 截取元素截图
            image_bytes = element.screenshot()

            # 使用 recognize 方法识别
            return self.recognize(image_bytes)

        except Exception as e:
            logger.error(f"❌ 从页面元素获取验证码失败 (selector: {selector}): {e}", exc_info=True)
            return None


class ManualCaptchaRecognizer(CaptchaRecognizer):
    """
    手动验证码识别器

    将验证码图片保存到磁盘，将任务置为 WAITING_FOR_CAPTCHA 状态，
    然后轮询等待用户通过 API 提交验证码答案。

    适用场景：ddddocr 识别率不足时，由人工介入完成验证码输入。

    Attributes:
        task: ScraperTask 实例，用于状态协调
        timeout: 等待超时秒数，默认 300 秒
        poll_interval: 轮询间隔秒数，默认 2 秒
    """

    _CAPTCHA_DIR = "automation/captcha_pending"

    def __init__(self, task: Any, timeout: int = 300, poll_interval: float = 2.0) -> None:
        self.task = task
        self.timeout = timeout
        self.poll_interval = poll_interval

    def recognize(self, image_bytes: bytes) -> str | None:  # pragma: no cover
        if not image_bytes:
            logger.warning("⚠️ 图片字节流为空")
            return None

        try:
            from django.conf import settings

            # 1. 保存验证码图片
            captcha_dir = Path(settings.MEDIA_ROOT) / self._CAPTCHA_DIR
            captcha_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{self.task.id}_{int(time.time() * 1000)}.png"
            image_path = captcha_dir / filename
            image_path.write_bytes(image_bytes)

            # 2. 更新任务状态
            from apps.automation.models import ScraperTaskStatus

            self.task.status = ScraperTaskStatus.WAITING_FOR_CAPTCHA
            self.task.captcha_image_path = str(image_path)
            self.task.captcha_answer = None
            self.task.error_message = "请手动输入验证码"
            self.task.save(update_fields=["status", "captcha_image_path", "captcha_answer", "error_message", "updated_at"])
            logger.info("📸 验证码图片已保存，等待手动输入: task=%s, path=%s", self.task.id, image_path)

            # 3. 轮询等待用户提交答案
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                time.sleep(self.poll_interval)
                self.task.refresh_from_db(fields=["captcha_answer", "status"])

                answer = self.task.captcha_answer
                if answer and answer.strip():
                    cleaned: str = answer.strip().replace(" ", "")
                    logger.info("✅ 收到手动验证码: task=%s, answer=%s", self.task.id, cleaned)

                    # 清理图片和状态
                    try:
                        image_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return cleaned

            # 4. 超时
            logger.warning("⏰ 手动验证码等待超时: task=%s, timeout=%ss", self.task.id, self.timeout)
            self.task.error_message = "手动验证码等待超时"
            self.task.save(update_fields=["error_message", "updated_at"])
            return None

        except Exception as e:
            logger.error("❌ 手动验证码识别异常: %s", e, exc_info=True)
            return None

    def recognize_from_element(self, page: Any, selector: str) -> str | None:  # pragma: no cover
        try:
            element = page.locator(selector)
            element.wait_for(state="visible", timeout=5000)
            image_bytes = element.screenshot()
            return self.recognize(image_bytes)
        except Exception as e:
            logger.error(f"❌ 从页面元素获取验证码失败 (selector: {selector}): {e}", exc_info=True)
            return None


def get_captcha_recognizer(task: Any = None) -> CaptchaRecognizer:
    """
    根据 CAPTCHA_AUTO_RECOGNIZE 全局配置返回合适的验证码识别器。

    - 配置为 true → DdddocrRecognizer（自动识别）
    - 配为 false 且有 task → ManualCaptchaRecognizer（手动输入）
    - 配为 false 但无 task → DdddocrRecognizer（兜底自动，因为手动模式需要 task 协调）

    Args:
        task: ScraperTask 实例（可选）。有 task 时可启用手动模式。

    Returns:
        CaptchaRecognizer 实例
    """
    from apps.core.services.system_config_service import SystemConfigService

    auto = SystemConfigService().get_value("CAPTCHA_AUTO_RECOGNIZE", "false").lower()
    if auto in ("true", "1", "yes"):
        logger.info("🔑 CAPTCHA_AUTO_RECOGNIZE=true，使用 DdddocrRecognizer")
        return DdddocrRecognizer(show_ad=False)

    if task is not None:
        logger.info("🔑 CAPTCHA_AUTO_RECOGNIZE=false，使用 ManualCaptchaRecognizer (task=%s)", getattr(task, "id", "?"))
        return ManualCaptchaRecognizer(task=task)

    logger.info("🔑 CAPTCHA_AUTO_RECOGNIZE=false 但无 task，兜底使用 DdddocrRecognizer")
    return DdddocrRecognizer(show_ad=False)
