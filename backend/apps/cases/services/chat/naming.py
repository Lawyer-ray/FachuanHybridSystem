"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
from typing import Any, cast

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


class ChatNameBuilder:
    def __init__(self, *, config_service: Any | None = None) -> None:
        self._config_service = config_service

    @property
    def config_service(self) -> Any:
        if self._config_service is None:
            from apps.cases.services.chat.chat_name_config_service import ChatNameConfigService

            self._config_service = ChatNameConfigService()
        return self._config_service

    def build(self, *, case: Any) -> str:
        if not case:
            raise ValidationException(
                message=_("案件对象不能为空"), code="INVALID_CASE", errors={"case": str(_("案件对象为必填项"))}
            )
        if not getattr(case, "name", None):
            raise ValidationException(
                message=_("案件名称不能为空"),
                code="INVALID_CASE_NAME",
                errors={"case_name": str(_("案件名称为必填项"))},
            )

        stage_display: str | None = None
        if getattr(case, "current_stage", None):
            try:
                stage_display = case.get_current_stage_display()
            except (AttributeError, ValueError):
                stage_display = case.current_stage
                logger.warning("无法获取案件阶段显示名称: %s, 使用原始值", case.current_stage)

        case_type_display: str | None = None
        if getattr(case, "case_type", None):
            try:
                case_type_display = case.get_case_type_display()
            except (AttributeError, ValueError):
                case_type_display = case.case_type
                logger.warning("无法获取案件类型显示名称: %s, 使用原始值", case.case_type)

        chat_name = self.config_service.render_chat_name(
            case_name=case.name, stage=stage_display, case_type=case_type_display
        )
        logger.debug("生成群聊名称: %s (案件ID: %s)", chat_name, getattr(case, 'id', None))
        return cast(str, chat_name)
