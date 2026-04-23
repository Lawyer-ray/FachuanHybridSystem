"""doc_convert 异常定义。"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions.base import BusinessException
from apps.core.exceptions.common import ValidationException

# 错误码常量
ERROR_ZNSZJ_DISABLED = "ZNSZJ_DISABLED"
ERROR_ZNSZJ_NOT_CONFIGURED = "ZNSZJ_NOT_CONFIGURED"
ERROR_INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
ERROR_INVALID_MBID = "INVALID_MBID"
ERROR_FILE_TOO_LARGE = "FILE_TOO_LARGE"
ERROR_ZNSZJ_UNAVAILABLE = "ZNSZJ_UNAVAILABLE"
ERROR_ZNSZJ_INVALID_RESPONSE = "ZNSZJ_INVALID_RESPONSE"


class ZnszjDisabledError(BusinessException):
    """znszj 功能未启用（HTTP 403）。"""

    status: int = 403

    def __init__(self) -> None:
        super().__init__(
            message=_("要素式转换功能未启用"),
            code=ERROR_ZNSZJ_DISABLED,
        )


class ZnszjNotConfiguredError(BusinessException):
    """znszj 私有实现未配置（HTTP 503）。"""

    status: int = 503

    def __init__(self) -> None:
        super().__init__(
            message=_("要素式转换功能未配置"),
            code=ERROR_ZNSZJ_NOT_CONFIGURED,
        )


class InvalidFileTypeError(ValidationException):
    """文件类型不支持（HTTP 400）。"""

    def __init__(self, *, filename: str, allowed_extensions: list[str]) -> None:
        super().__init__(
            message=_("不支持的文件类型，仅支持：%(exts)s") % {"exts": ", ".join(allowed_extensions)},
            code=ERROR_INVALID_FILE_TYPE,
            errors={"filename": filename},
        )


class InvalidMbidError(ValidationException):
    """无效的 mbid（HTTP 400）。"""

    def __init__(self, *, mbid: str) -> None:
        super().__init__(
            message=_("无效的文书类型：%(mbid)s") % {"mbid": mbid},
            code=ERROR_INVALID_MBID,
            errors={"mbid": mbid},
        )


class FileTooLargeError(ValidationException):
    """文件过大（HTTP 400）。"""

    def __init__(self, *, size_mb: float, max_size_mb: int = 20) -> None:
        super().__init__(
            message=_("文件大小超过限制（%(size).2fMB > %(max)dMB）") % {"size": size_mb, "max": max_size_mb},
            code=ERROR_FILE_TOO_LARGE,
            errors={"size_mb": size_mb, "max_size_mb": max_size_mb},
        )


class ZnszjUnavailableError(BusinessException):
    """znszj 系统不可用（HTTP 502）。"""

    status: int = 502

    def __init__(self, *, detail: str | None = None) -> None:
        super().__init__(
            message=_("要素式转换服务暂时不可用"),
            code=ERROR_ZNSZJ_UNAVAILABLE,
            errors={"detail": detail} if detail else {},
        )


class ZnszjInvalidResponseError(BusinessException):
    """znszj 返回格式异常（HTTP 502）。"""

    status: int = 502

    def __init__(self, *, detail: str | None = None) -> None:
        super().__init__(
            message=_("要素式转换服务返回异常"),
            code=ERROR_ZNSZJ_INVALID_RESPONSE,
            errors={"detail": detail} if detail else {},
        )
