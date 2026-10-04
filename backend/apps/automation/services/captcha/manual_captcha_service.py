"""手动验证码服务。

承载 captcha_manual_api 下沉的业务：等待验证码状态的任务定位、验证码
图片读取、答案写入与任务恢复（WAITING_FOR_CAPTCHA → RUNNING）。

失败语义沿用 API 时期的约定——不抛异常，返回带错误信息的结果对象
（图片端点为 ``CaptchaImagePayload`` 的 error_status/error_message，
答案端点为 ``CaptchaAnswerResult`` 的 success=False + message），由
API 层组装原样的 HttpResponse / CaptchaAnswerOut 响应。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import IO

logger = logging.getLogger("apps.automation")


@dataclass
class CaptchaImagePayload:
    """验证码图片读取结果：error 或二选一的已打开文件对象。"""

    error_status: int | None = None
    error_message: str | None = None
    file_obj: IO[bytes] | None = None


@dataclass
class CaptchaAnswerResult:
    """验证码答案提交结果。"""

    success: bool
    message: str


class ManualCaptchaService:
    """手动验证码模式下的任务定位、图片读取与答案回写。"""

    async def get_captcha_image(self, task_id: int) -> CaptchaImagePayload:
        """获取待识别验证码图片（仅 WAITING_FOR_CAPTCHA 状态可用）。

        Returns:
            任务不存在/状态不符/图片缺失时返回对应 error_status(404/400)，
            成功时返回已打开的 PNG 文件对象。
        """
        from apps.automation.models import ScraperTask, ScraperTaskStatus

        try:
            task = await ScraperTask.objects.aget(id=task_id)
        except ScraperTask.DoesNotExist:
            return CaptchaImagePayload(error_status=404, error_message="任务不存在")

        if task.status != ScraperTaskStatus.WAITING_FOR_CAPTCHA:
            return CaptchaImagePayload(error_status=400, error_message="当前任务不在等待验证码状态")

        image_path = task.captcha_image_path
        if not image_path:
            return CaptchaImagePayload(error_status=404, error_message="验证码图片不存在")

        try:
            file_obj = await asyncio.to_thread(open, image_path, "rb")
        except FileNotFoundError:
            return CaptchaImagePayload(error_status=404, error_message="验证码图片文件已丢失")
        return CaptchaImagePayload(file_obj=file_obj)

    async def submit_answer(self, task_id: int, answer: str) -> CaptchaAnswerResult:
        """提交验证码答案，写入任务记录并恢复为 RUNNING。

        后台 ManualCaptchaRecognizer 会轮询检测到答案并继续执行。
        """
        from apps.automation.models import ScraperTask, ScraperTaskStatus

        try:
            task = await ScraperTask.objects.aget(id=task_id)
        except ScraperTask.DoesNotExist:
            return CaptchaAnswerResult(success=False, message="任务不存在")

        if task.status != ScraperTaskStatus.WAITING_FOR_CAPTCHA:
            return CaptchaAnswerResult(success=False, message=f"当前任务状态为 {task.status}，不在等待验证码状态")

        stripped = answer.strip()
        if not stripped:
            return CaptchaAnswerResult(success=False, message="验证码答案不能为空")

        task.captcha_answer = stripped
        task.status = ScraperTaskStatus.RUNNING
        task.error_message = ""
        await task.asave(update_fields=["captcha_answer", "status", "error_message", "updated_at"])

        logger.info("✅ 验证码答案已提交: task=%s", task_id)
        return CaptchaAnswerResult(success=True, message="验证码已提交，任务继续执行")
