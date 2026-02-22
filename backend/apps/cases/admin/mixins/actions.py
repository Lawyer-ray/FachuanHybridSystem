"""Module for actions."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.cases.exceptions import ChatProviderException
from apps.cases.models import Case
from apps.core.enums import ChatPlatform

from .service import CaseAdminServiceMixin

logger = logging.getLogger(__name__)


class CaseAdminActionsMixin(CaseAdminServiceMixin):
    def response_change(self, request: HttpRequest, obj: Case) -> HttpResponse:
        if "_save_and_duplicate" in request.POST:
            try:
                service = self._get_case_admin_service()
                new_case = service.duplicate_case(obj.pk)
                messages.success(request, _("已复制案件,正在编辑新案件: %s") % new_case.name)
                return HttpResponseRedirect(reverse("admin:cases_case_change", args=[new_case.pk]))
            except Exception as e:
                logger.exception("操作失败")
                messages.error(request, _("复制失败: %s") % str(e))
                return HttpResponseRedirect(request.path)

        if "_save" in request.POST:
            messages.success(request, _("案件「%s」已保存") % obj.name)
            return HttpResponseRedirect(reverse("admin:cases_case_detail", args=[obj.pk]))

        if "_continue" in request.POST:
            return super().response_change(request, obj)  # type: ignore[misc, no-any-return]

        return super().response_change(request, obj)  # type: ignore[misc, no-any-return]

    def create_feishu_chat_for_selected_cases(self, request: HttpRequest, queryset: QuerySet[Case, Case]) -> None:
        service = self._get_case_chat_service()
        success_count = 0
        error_count = 0

        for case in queryset:
            try:
                existing_chat = case.chats.filter(platform=ChatPlatform.FEISHU, is_active=True).first()

                if existing_chat:
                    messages.warning(
                        request,
                        _("案件 %(case)s 已存在飞书群聊: %(chat)s")
                        % {"case": case.name, "chat": existing_chat.name},
                    )
                    continue

                chat = service.create_chat_for_case(case.id, ChatPlatform.FEISHU)
                success_count += 1

                messages.success(
                    request,
                    _("成功为案件 %(case)s 创建飞书群聊: %(chat)s")
                    % {"case": case.name, "chat": chat.name},
                )

            except ChatProviderException as e:
                error_count += 1
                messages.error(
                    request,
                    _("为案件 %(case)s 创建飞书群聊失败: %(error)s")
                    % {"case": case.name, "error": str(e)},
                )
            except Exception as e:
                logger.exception("操作失败")
                error_count += 1
                messages.error(
                    request,
                    _("为案件 %(case)s 创建群聊时发生未知错误: %(error)s")
                    % {"case": case.name, "error": str(e)},
                )

        if success_count > 0:
            messages.success(request, _("总计成功创建 %d 个飞书群聊") % success_count)

        if error_count > 0:
            messages.error(request, _("总计 %d 个案件创建群聊失败") % error_count)

    create_feishu_chat_for_selected_cases.short_description = _("为选中案件创建飞书群聊")  # type: ignore[attr-defined]


__all__: list[str] = ["CaseAdminActionsMixin"]
