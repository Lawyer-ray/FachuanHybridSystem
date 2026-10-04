"""
验证码识别 API

提供验证码识别的 HTTP 接口，支持 Base64 编码的图片上传。
"""

import logging
from typing import Any

from ninja import Router

from apps.automation.schemas import CaptchaRecognizeIn, CaptchaRecognizeOut
from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger("apps.automation")

router = Router(tags=["验证码识别"])


def _get_captcha_service() -> Any:
    from apps.core.dependencies import build_captcha_service

    return build_captcha_service()


# NOTE:
# 该接口用于自动化流程中的验证码识别，必须保持“无认证、无 CSRF”——
# 浏览器自动化与脚本直接调用，加 auth/CSRF 会导致其回归 403/401。
# 2026-10 安全审计第4轮：接口已随服务公网暴露，原“无速率限制”的约定废止，
# 现叠加 IP 级限流（复用既有的 UPLOAD bucket：匿名请求按来源 IP 计数，
# 已认证请求按用户计数），防止公网匿名刷量占用 OCR 资源。
@router.post("/recognize", response=CaptchaRecognizeOut, auth=None)
@rate_limit_from_settings("UPLOAD")
def recognize_captcha(request: Any, payload: CaptchaRecognizeIn) -> CaptchaRecognizeOut:  # pragma: no cover
    """
    识别验证码

    接收 Base64 编码的图片，返回识别结果。

    **支持的图片格式**: PNG, JPEG, GIF, BMP

    **图片大小限制**: 最大 5MB

    **请求示例**:
    ```json
    {
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAUA..."
    }
    ```

    **成功响应示例**:
    ```json
    {
        "success": true,
        "text": "AB12",
        "processing_time": 0.234,
        "error": null
    }
    ```

    **失败响应示例**:
    ```json
    {
        "success": false,
        "text": null,
        "processing_time": 0.012,
        "error": "图片格式不支持"
    }
    ```

    Args:
        request: HTTP 请求对象
        payload: 验证码识别请求数据

    Returns:
        CaptchaRecognizeOut: 识别结果，包含成功状态、文本、处理时间和错误信息
    """
    logger.info("收到验证码识别请求")

    # 创建服务实例并执行识别（使用工厂函数）
    service = _get_captcha_service()
    result = service.recognize_from_base64(payload.image_base64)

    if result.success:
        logger.info("验证码识别成功: text=%s, processing_time=%.3fs", result.text, result.processing_time)
    else:
        logger.warning("验证码识别失败: error=%s, processing_time=%.3fs", result.error, result.processing_time)

    return CaptchaRecognizeOut(
        success=result.success,
        text=result.text,
        processing_time=result.processing_time,
        error=result.error,
    )
