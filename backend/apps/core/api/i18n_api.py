from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema
from ninja.responses import Response

from apps.core.security.auth import JWTOrSessionAuth

logger = logging.getLogger(__name__)

i18n_router = Router(tags=["国际化"])


class LanguageSchema(Schema):
    language: str


class LanguageItemSchema(Schema):
    code: str
    name: str


def _get_i18n_service() -> Any:
    from apps.core.services.i18n_service import I18nService

    return I18nService()


@i18n_router.get("/languages", response=list[LanguageItemSchema], auth=None)
def list_languages(request: HttpRequest) -> list[dict[str, str]]:
    """返回系统支持的语言列表"""
    result: list[dict[str, str]] = _get_i18n_service().get_supported_languages()
    return result


@i18n_router.post("/language", response={200: dict[str, str]}, auth=JWTOrSessionAuth())
def set_language(request: HttpRequest, payload: LanguageSchema) -> dict[str, str]:
    """设置用户语言偏好"""
    _get_i18n_service().set_language(request, payload.language)
    return {"language": payload.language}
