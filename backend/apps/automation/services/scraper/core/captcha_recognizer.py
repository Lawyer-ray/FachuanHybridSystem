"""
验证码识别器接口

提供可插拔的验证码识别功能，支持多种识别服务。
"""

import logging
import time
import uuid
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


class ManualCaptchaRecognizer(CaptchaRecognizer):
    """
    手动验证码识别器

    将验证码图片保存到磁盘，将任务置为 WAITING_FOR_CAPTCHA 状态，
    然后轮询等待用户通过 API 提交验证码答案。

    适用场景：由人工介入完成验证码输入，适用于所有验证码场景。

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


class FileBasedCaptchaRecognizer(CaptchaRecognizer):
    """
    基于文件系统的验证码识别器（无 task 依赖）

    将验证码图片保存到临时目录，并创建一个 .answer 文件等待用户输入。
    适用场景：消息中心同步等没有 ScraperTask 的场景。

    工作流程：
    1. 保存验证码图片到 {_CAPTCHA_DIR}/{uuid}.png
    2. 创建 {_CAPTCHA_DIR}/{uuid}.answer 空文件
    3. 轮询等待 .answer 文件中出现内容
    4. 用户写入答案后返回

    Attributes:
        timeout: 等待超时秒数，默认 300 秒
        poll_interval: 轮询间隔秒数，默认 2 秒
    """

    _CAPTCHA_DIR = "automation/captcha_pending"

    def __init__(self, timeout: int = 300, poll_interval: float = 2.0) -> None:
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
            captcha_id = uuid.uuid4().hex[:12]
            filename = f"{captcha_id}.png"
            image_path = captcha_dir / filename
            image_path.write_bytes(image_bytes)

            # 2. 创建 .answer 文件（用户需要写入答案）
            answer_path = captcha_dir / f"{captcha_id}.answer"
            answer_path.write_text("", encoding="utf-8")

            logger.info(
                "📸 验证码图片已保存，等待手动输入:\n"
                "  图片: %s\n"
                "  答案文件: %s\n"
                "  请将验证码写入 .answer 文件",
                image_path,
                answer_path,
            )

            # 3. 轮询等待答案文件有内容
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                time.sleep(self.poll_interval)

                if answer_path.exists():
                    answer = answer_path.read_text(encoding="utf-8").strip()
                    if answer:
                        cleaned: str = answer.strip().replace(" ", "")
                        logger.info("✅ 收到手动验证码: captcha_id=%s, answer=%s", captcha_id, cleaned)

                        # 清理文件
                        try:
                            image_path.unlink(missing_ok=True)
                            answer_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return cleaned

            # 4. 超时
            logger.warning("⏰ 手动验证码等待超时: captcha_id=%s, timeout=%ss", captcha_id, self.timeout)
            try:
                image_path.unlink(missing_ok=True)
                answer_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

        except Exception as e:
            logger.error("❌ 文件验证码识别异常: %s", e, exc_info=True)
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
    根据插件可用性和 task 参数返回合适的验证码识别器。

    优先级：
    1. captcha_ocr 插件已安装且 ddddocr 可用 → DdddocrRecognizer（自动识别）
    2. 有 task 参数 → ManualCaptchaRecognizer（手动输入，依赖 task 状态）
    3. 无 task 且插件不可用 → FileBasedCaptchaRecognizer（基于文件的手动输入）

    Args:
        task: ScraperTask 实例（可选）。有 task 时可启用 task-based 手动模式。

    Returns:
        CaptchaRecognizer 实例
    """
    # 1. 尝试自动识别插件
    try:
        from plugins import has_captcha_ocr_plugin  # type: ignore[attr-defined]

        if has_captcha_ocr_plugin():
            from plugins.captcha_ocr import DdddocrRecognizer

            logger.info("captcha_ocr 插件已安装，使用 DdddocrRecognizer")
            return cast(CaptchaRecognizer, DdddocrRecognizer(show_ad=False))
    except ImportError:
        pass  # plugins 子模块未安装，静默降级
    except Exception as e:
        # ddddocr 库未安装等其他异常
        logger.debug("captcha_ocr 插件加载失败: %s", e)

    # 2. 有 task 时使用 task-based 手动模式
    if task is not None:
        logger.info("使用 ManualCaptchaRecognizer (task=%s)", getattr(task, "id", "?"))
        return ManualCaptchaRecognizer(task=task)

    # 3. 无 task 时使用基于文件的手动模式
    logger.info("使用 FileBasedCaptchaRecognizer（无 task，基于文件系统等待手动输入）")
    return FileBasedCaptchaRecognizer()
