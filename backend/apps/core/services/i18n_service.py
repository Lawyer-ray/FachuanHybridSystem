from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.core")


class I18nService:
    """语言切换服务"""

    def get_supported_languages(self) -> list[dict[str, str]]:
        """返回系统支持的语言列表"""
        languages: list[dict[str, str]] = [
            {"code": code, "name": str(name)}
            for code, name in settings.LANGUAGES
        ]
        logger.info("获取支持语言列表", extra={"count": len(languages)})
        return languages

    def set_language(self, request: Any, language_code: str) -> None:
        """
        设置用户语言偏好到 session

        Args:
            request: Django HttpRequest
            language_code: 语言代码，如 "zh-hans" 或 "en"

        Raises:
            ValidationException: 不支持的语言代码
        """
        supported = [code for code, _ in settings.LANGUAGES]
        if language_code not in supported:
            raise ValidationException(
                message=_("不支持的语言代码"),
                code="UNSUPPORTED_LANGUAGE",
                errors={"language": language_code, "supported": supported},
            )
        translation.activate(language_code)
        request.session[translation.LANGUAGE_SESSION_KEY] = language_code
        logger.info(
            "设置用户语言偏好",
            extra={"language": language_code, "user": getattr(request, "user", None)},
        )
