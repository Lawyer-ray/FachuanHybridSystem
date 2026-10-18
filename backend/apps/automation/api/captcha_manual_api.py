"""
手动验证码 API

提供手动验证码模式下的图片获取和答案提交接口。
当 CAPTCHA_AUTO_RECOGNIZE=false 时，scraper 任务会进入等待验证码状态，
前端通过这些接口展示验证码图片并接收用户输入。
"""

from typing import Any

from django.http import FileResponse, HttpResponse
from ninja import Router, Schema

from apps.automation.services.captcha.manual_captcha_service import ManualCaptchaService

router = Router(tags=["手动验证码"])


def _get_manual_captcha_service() -> ManualCaptchaService:
    """工厂函数：创建手动验证码服务实例。"""
    return ManualCaptchaService()


def _ensure_operator(request: Any) -> None:
    """安全审计（2026-10-19）：ScraperTask 无属主字段，验证码读/答若不限权，
    任意登录用户可读取他人等待中任务的验证码图并抢答/错答，令法院文书下载反复失败。
    收敛为管理员口径。"""
    from apps.core.exceptions import PermissionDenied
    from apps.core.security.admin_access import get_request_user, is_admin_user

    if not is_admin_user(get_request_user(request)):
        raise PermissionDenied(message="仅管理员可处理手动验证码", code="PERMISSION_DENIED")


class CaptchaAnswerIn(Schema):
    """验证码答案提交"""

    answer: str


class CaptchaAnswerOut(Schema):
    """验证码答案提交结果"""

    success: bool
    message: str


@router.get("/{task_id}/image")  # 安全审计 B-32：去掉 auth=None，未认证者不可读图/劫持任务
async def get_captcha_image(request: Any, task_id: int) -> HttpResponse | FileResponse:
    """
    获取待识别验证码图片

    返回 PNG 格式的验证码图片。仅当任务处于 WAITING_FOR_CAPTCHA 状态时可用。
    """
    _ensure_operator(request)
    payload = await _get_manual_captcha_service().get_captcha_image(task_id)
    if payload.error_status is not None:
        return HttpResponse(payload.error_message, status=payload.error_status)
    assert payload.file_obj is not None
    return FileResponse(payload.file_obj, content_type="image/png")


@router.post("/{task_id}/answer", response=CaptchaAnswerOut)  # 安全审计 B-32
async def submit_captcha_answer(request: Any, task_id: int, payload: CaptchaAnswerIn) -> CaptchaAnswerOut:
    """
    提交验证码答案

    将用户输入的验证码写入任务记录，并恢复任务为 RUNNING 状态。
    后台 ManualCaptchaRecognizer 会轮询检测到答案并继续执行。
    """
    _ensure_operator(request)
    result = await _get_manual_captcha_service().submit_answer(task_id, payload.answer)
    return CaptchaAnswerOut(success=result.success, message=result.message)
