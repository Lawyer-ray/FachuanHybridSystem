"""
验证码识别 API

提供验证码识别的 HTTP 接口，支持 Base64 编码的图片上传。
"""

import logging
from typing import Any

from ninja import Router

from apps.automation.schemas import CaptchaRecognizeIn, CaptchaRecognizeOut

logger = logging.getLogger("apps.automation")

router = Router(tags=["验证码识别"])


def _get_captcha_service() -> Any:
    from apps.core.dependencies import build_captcha_service

    return build_captcha_service()


@router.post("/recognize", response=CaptchaRecognizeOut)
def recognize_captcha(request: Any, payload: CaptchaRecognizeIn) -> CaptchaRecognizeOut:
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
        logger.info(f"验证码识别成功: text={result.text}, processing_time={result.processing_time:.3f}s")
    else:
        logger.warning(f"验证码识别失败: error={result.error}, processing_time={result.processing_time:.3f}s")

    return CaptchaRecognizeOut(
        success=result.success,
        text=result.text,
        processing_time=result.processing_time,
        error=result.error,
    )
