"""Business logic services."""

from django.utils.translation import gettext_lazy as _
import base64

from apps.core.exceptions import ValidationException


def decode_base64_payload(data: str) -> bytes:
    try:
        value = data or ""
        if "," in value:
            value = value.split(",", 1)[1]
        return base64.b64decode(value)
    except Exception as e:
        raise ValidationException(message=_("图片数据解码失败"), code="IMAGE_DECODE_FAILED", errors={}) from e


def validate_image_format(*, img_format: str, supported_formats: set[str]) -> str:
    value = (img_format or "jpeg").lower()
    if value not in supported_formats:
        raise ValidationException(message=f"不支持的图片格式: {value}", code="UNSUPPORTED_FORMAT", errors={})
    return value


def validate_file_size(*, image_bytes: bytes, max_file_size: int) -> None:
    if len(image_bytes) > max_file_size:
        raise ValidationException(
            message=f"文件大小超过 {max_file_size // (1024 * 1024)}MB 限制", code="FILE_TOO_LARGE", errors={}
        )
