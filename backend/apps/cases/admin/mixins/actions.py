"""Module for actions."""

import logging

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.cases.exceptions import ChatProviderException
from apps.core.enums import ChatPlatform

from .views import CaseAdminServiceMixin

logger = logging.getLogger(__name__)


class CaseAdminActionsMixin(CaseAdminServiceMixin):
    def response_change(self, request, obj) -> None:
        if "_save_and_duplicate" in request.POST:
            try:
                service = self._get_case_admin_service()
                new_case = service.duplicate_case(obj.pk)
                messages.success(request, f"已复制案件,正在编辑新案件: {new_case.name}")
                return HttpResponseRedirect(reverse("admin:cases_case_change", args=[new_case.pk]))
            except Exception as e:
                logger.exception("操作失败")
                messages.error(request, f"复制失败: {e!s}")
                return HttpResponseRedirect(request.path)

        if "_save" in request.POST:
            messages.success(request, f"案件「{obj.name}」已保存")
            return HttpResponseRedirect(reverse("admin:cases_case_detail", args=[obj.pk]))

        if "_continue" in request.POST:
            return super().response_change(request, obj)

        return super().response_change(request, obj)

    def create_feishu_chat_for_selected_cases(self, request, queryset) -> None:
        service = self._get_case_chat_service()
        success_count = 0
        error_count = 0

        for case in queryset:
            try:
                existing_chat = case.chats.filter(platform=ChatPlatform.FEISHU, is_active=True).first()

                if existing_chat:
                    messages.warning(request, f"案件 {case.name} 已存在飞书群聊: {existing_chat.name}")
                    continue

                chat = service.create_chat_for_case(case.id, ChatPlatform.FEISHU)
                success_count += 1

                messages.success(request, f"成功为案件 {case.name} 创建飞书群聊: {chat.name}")

            except ChatProviderException as e:
                error_count += 1
                messages.error(request, f"为案件 {case.name} 创建飞书群聊失败: {e!s}")
            except Exception as e:
                logger.exception("操作失败")
                error_count += 1
                messages.error(request, f"为案件 {case.name} 创建群聊时发生未知错误: {e!s}")

        if success_count > 0:
            messages.success(request, f"总计成功创建 {success_count} 个飞书群聊")

        if error_count > 0:
            messages.error(request, f"总计 {error_count} 个案件创建群聊失败")

    create_feishu_chat_for_selected_cases.short_description = _("为选中案件创建飞书群聊")


__all__: list[str] = ["CaseAdminActionsMixin"]
