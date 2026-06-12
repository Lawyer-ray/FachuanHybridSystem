"""
手动验证码 API

提供手动验证码模式下的图片获取和答案提交接口。
当 CAPTCHA_AUTO_RECOGNIZE=false 时，scraper 任务会进入等待验证码状态，
前端通过这些接口展示验证码图片并接收用户输入。
"""

import logging
from typing import Any

from django.http import FileResponse, HttpResponse
from ninja import Router, Schema

logger = logging.getLogger("apps.automation")

router = Router(tags=["手动验证码"])


class CaptchaAnswerIn(Schema):
    """验证码答案提交"""
    answer: str


class CaptchaAnswerOut(Schema):
    """验证码答案提交结果"""
    success: bool
    message: str


@router.get("/{task_id}/image", auth=None)
def get_captcha_image(request: Any, task_id: int) -> HttpResponse:
    """
    获取待识别验证码图片

    返回 PNG 格式的验证码图片。仅当任务处于 WAITING_FOR_CAPTCHA 状态时可用。
    """
    from apps.automation.models import ScraperTask, ScraperTaskStatus

    try:
        task = ScraperTask.objects.get(id=task_id)
    except ScraperTask.DoesNotExist:
        return HttpResponse("任务不存在", status=404)

    if task.status != ScraperTaskStatus.WAITING_FOR_CAPTCHA:
        return HttpResponse("当前任务不在等待验证码状态", status=400)

    image_path = task.captcha_image_path
    if not image_path:
        return HttpResponse("验证码图片不存在", status=404)

    try:
        return FileResponse(open(image_path, "rb"), content_type="image/png")
    except FileNotFoundError:
        return HttpResponse("验证码图片文件已丢失", status=404)


@router.post("/{task_id}/answer", response=CaptchaAnswerOut, auth=None)
def submit_captcha_answer(request: Any, task_id: int, payload: CaptchaAnswerIn) -> CaptchaAnswerOut:
    """
    提交验证码答案

    将用户输入的验证码写入任务记录，并恢复任务为 RUNNING 状态。
    后台 ManualCaptchaRecognizer 会轮询检测到答案并继续执行。
    """
    from apps.automation.models import ScraperTask, ScraperTaskStatus

    try:
        task = ScraperTask.objects.get(id=task_id)
    except ScraperTask.DoesNotExist:
        return CaptchaAnswerOut(success=False, message="任务不存在")

    if task.status != ScraperTaskStatus.WAITING_FOR_CAPTCHA:
        return CaptchaAnswerOut(success=False, message=f"当前任务状态为 {task.status}，不在等待验证码状态")

    answer = payload.answer.strip()
    if not answer:
        return CaptchaAnswerOut(success=False, message="验证码答案不能为空")

    task.captcha_answer = answer
    task.status = ScraperTaskStatus.RUNNING
    task.error_message = None
    task.save(update_fields=["captcha_answer", "status", "error_message", "updated_at"])

    logger.info("✅ 验证码答案已提交: task=%s", task_id)
    return CaptchaAnswerOut(success=True, message="验证码已提交，任务继续执行")
