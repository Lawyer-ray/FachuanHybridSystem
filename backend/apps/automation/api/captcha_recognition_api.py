"""
验证码识别 API

提供验证码识别的 HTTP 接口，支持 Base64 编码的图片上传。
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from django.conf import settings
from ninja import Router

from apps.automation.schemas import CaptchaRecognizeIn, CaptchaRecognizeOut
from apps.core.exceptions import PermissionDenied
from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger("apps.automation")

router = Router(tags=["验证码识别"])

# 服务间共享密钥的请求头名。选自定义头而非 Authorization：本端点对浏览器
# 侧无凭证，自定义头不会触发 CORS 预检（Ninja 的 CORS 配置里也没放行它），
# 且不会与用户的 JWT 语义混淆。
CAPTCHA_SECRET_HEADER = "HTTP_X_CAPTCHA_SECRET"  # pragma: allowlist secret


def _get_captcha_service() -> Any:
    from apps.core.dependencies import build_captcha_service

    return build_captcha_service()


def _authorize_service_call(request: Any) -> None:
    """校验服务间共享密钥（安全审计 M-5）。

    **背景**：该端点原先 ``auth=None``，任何匿名请求都能把图片送进来免费 OCR。
    它随服务一起暴露在公网（cloudflared 隧道），而仓库内**没有任何调用方**
    走 HTTP 打它——浏览器自动化与插件全部进程内直连
    ``CaptchaServiceAdapter`` / ``build_captcha_service()``。也就是说这个
    HTTP 端点没有内部消费者，匿名开放等于白送算力。

    **方案**：要求调用方带 ``X-Captcha-Secret`` 头，值等于
    ``CAPTCHA_RECOGNIZE_SECRET``（环境变量配置）。

    - **未配置密钥** → 端点整体不可用（403）。生产忘配时是「功能不可用」而
      不是「匿名可刷」，符合 fail-closed；
    - 密钥比对用 ``hmac.compare_digest``，避免时序侧信道；
    - 密钥本身不记入日志，只记命中/未命中。

    **为什么不用 JWT 认证**：调用方是脚本/浏览器自动化，拿不到也不该拿用户
    身份的 JWT；服务间共享密钥才是这个场景的正确模型。
    """
    expected = (getattr(settings, "CAPTCHA_RECOGNIZE_SECRET", "") or "").strip()
    if not expected:
        logger.warning("captcha_recognize_secret_not_configured")
        raise PermissionDenied(message="验证码识别服务未启用", code="CAPTCHA_SERVICE_DISABLED")

    provided = request.META.get(CAPTCHA_SECRET_HEADER) or ""
    if not hmac.compare_digest(str(provided).strip(), expected):
        logger.info("captcha_recognize_secret_mismatch")
        raise PermissionDenied(message="无效的调用凭证", code="CAPTCHA_SECRET_INVALID")


# NOTE:
# 该接口用于自动化流程中的验证码识别。历史上保持“无认证、无 CSRF”是为了让
# 浏览器自动化与脚本直接调用——但加 auth 会回归 403/401 的前提是「调用方
# 确实需要匿名」，而实际上仓库内没有任何调用方走 HTTP 打这个端点（全部进程内
# 直连 service）。
#
# 2026-10 安全审计：
# - 第 4 轮：接口已随服务公网暴露，原“无速率限制”的约定废止，叠加 IP 级限流
#   （复用 UPLOAD bucket：匿名按来源 IP，已认证按用户），防刷量占 OCR 资源；
# - 第 5 轮（M-5）：限流只是限流，不是认证——公网仍可当免费 OCR 用。改为要求
#   服务间共享密钥（见 _authorize_service_call），未配置密钥时端点整体不可用。
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
    # 先校验服务间共享密钥，再做任何 OCR 工作——未通过就不该消耗算力
    _authorize_service_call(request)

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
