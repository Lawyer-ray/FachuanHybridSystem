"""
法院短信 Admin 操作和功能视图

包含管理操作、案件指定、搜索、重试等功能视图.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.automation.models import CourtSMS

logger = logging.getLogger("apps.automation")


def _get_court_sms_service() -> Any:
    """获取法院短信服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_court_sms_service()


def _get_case_service() -> Any:
    """获取案件服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_case_service()


class CourtSMSAdminActions:
    """法院短信 Admin 操作混入类"""

    # 自定义操作
    actions: list[str] = []

    @admin.action(description=_("🔄 重新处理选中的短信"))
    def retry_processing_action(self, request: HttpRequest, queryset: QuerySet[CourtSMS]) -> None:
        """重新处理操作"""
        service = _get_court_sms_service()
        success_count = 0
        error_count = 0

        for sms in queryset:
            try:
                service.retry_processing(cast(int, sms.id))
                success_count += 1
                logger.info(f"管理员重新处理短信: SMS ID={sms.id}, User={request.user}")
            except Exception as e:
                error_count += 1
                logger.error(f"管理员重新处理短信失败: SMS ID={sms.id}, 错误: {e!s}")

        if success_count > 0:
            messages.success(request, f"成功重新处理 {success_count} 条短信")
        if error_count > 0:
            messages.error(request, f"重新处理失败 {error_count} 条短信")

    def submit_sms_view(self, request: HttpRequest) -> HttpResponse:
        """短信提交页面"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            received_at = request.POST.get("received_at")

            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()

                    received_datetime = None
                    if received_at:
                        from django.utils.dateparse import parse_datetime

                        received_datetime = parse_datetime(received_at)

                    sms = service.submit_sms(content, received_datetime)

                    messages.success(request, f"短信提交成功!记录ID: {sms.id}")
                    logger.info(f"管理员提交短信: SMS ID={sms.id}, User={request.user}")

                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[cast(int, sms.id)]))

                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
                    logger.error(f"管理员提交短信失败: User={request.user}, 错误: {e!s}")

        recent_sms = CourtSMS.objects.order_by("-created_at")[:10]

        context: dict[str, Any] = {
            "title": "提交法院短信",
            "recent_sms": recent_sms,
            "opts": self.model._meta,  # type: ignore[attr-defined]
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/submit_sms.html", context)

    def _get_suggested_cases(self, sms: CourtSMS, case_service: Any, sms_id: int) -> list[Any]:
        """获取推荐案件"""
        suggested_cases: list[Any] = []
        try:
            if sms.party_names:
                for party_name in sms.party_names:
                    if party_name.strip():
                        suggested_cases.extend(case_service.search_cases_by_party_internal([party_name.strip()])[:5])
            if sms.case_numbers:
                for case_number in sms.case_numbers:
                    if case_number.strip():
                        suggested_cases.extend(
                            case_service.search_cases_by_case_number_internal(case_number.strip())[:5]
                        )
            seen_ids: set[int] = set()
            unique: list[Any] = []
            for case in suggested_cases:
                if hasattr(case, "id") and cast(int, case.id) not in seen_ids:
                    seen_ids.add(cast(int, case.id))
                    unique.append(case)
            return unique[:10]
        except Exception as e:
            logger.warning(f"获取推荐案件失败: SMS ID={sms_id}, 错误: {e!s}")
            return []

    def _format_case_for_template(self, case_dto: Any) -> dict[str, Any]:
        """将 CaseDTO 转换为模板可用的格式"""
        try:
            case_service = _get_case_service()
            case_detail = case_service.get_case_detail_internal(cast(int, case_dto.id))
            return {
                "id": cast(int, case_detail.id),
                "name": case_detail.name,
                "created_at": cast(Any, case_detail.created_at),
                "case_numbers": getattr(case_detail, "case_numbers", []),
                "parties": getattr(case_detail, "parties", []),
            }
        except Exception as e:
            logger.warning(f"格式化案件数据失败: Case ID={case_dto.id}, 错误: {e!s}")
            return {
                "id": cast(int, case_dto.id),
                "name": case_dto.name,
                "created_at": None,
                "case_numbers": [],
                "parties": [],
            }

    def assign_case_view(self, request: HttpRequest, sms_id: int) -> HttpResponse:
        """手动指定案件页面"""
        sms = get_object_or_404(CourtSMS, id=sms_id)

        if request.method == "POST":
            case_id = request.POST.get("case_id")
            if not case_id:
                messages.error(request, "请选择一个案件")
            else:
                try:
                    service = _get_court_sms_service()
                    service.assign_case(sms_id, int(case_id))
                    messages.success(request, "案件指定成功!已触发文书重命名和推送通知流程")
                    logger.info(f"管理员手动指定案件: SMS ID={sms_id}, Case ID={case_id}, User={request.user}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))
                except Exception as e:
                    messages.error(request, f"指定案件失败: {e!s}")
                    logger.error(f"管理员手动指定案件失败: SMS ID={sms_id}, Case ID={case_id}, 错误: {e!s}")

        case_service = _get_case_service()
        suggested_cases = self._get_suggested_cases(sms, case_service, sms_id)

        context: dict[str, Any] = {
            "title": f"为短信 #{sms_id} 指定案件",
            "sms": sms,
            "suggested_cases": [self._format_case_for_template(c) for c in suggested_cases],
            "recent_cases": [],
            "opts": self.model._meta,  # type: ignore[attr-defined]
            "has_view_permission": True,
        }
        return render(request, "admin/automation/courtsms/assign_case.html", context)

    def search_cases_ajax(self, request: HttpRequest, sms_id: int) -> JsonResponse:
        """AJAX 案件搜索接口"""
        if request.method != "GET":
            return JsonResponse({"error": "只支持 GET 请求"}, status=405)

        search_term = request.GET.get("q", "").strip()
        if not search_term:
            return JsonResponse({"cases": []})

        try:
            case_service = _get_case_service()

            found_cases: list[Any] = []

            party_cases = case_service.search_cases_by_party_internal([search_term])[:10]
            found_cases.extend(party_cases)

            number_cases = case_service.search_cases_by_case_number_internal(search_term)[:10]
            found_cases.extend(number_cases)

            seen_ids: set[int] = set()
            unique_cases: list[Any] = []
            for case in found_cases:
                if hasattr(case, "id") and cast(int, case.id) not in seen_ids:
                    seen_ids.add(cast(int, case.id))
                    unique_cases.append(case)

            unique_cases = unique_cases[:15]

            cases_data: list[dict[str, Any]] = []
            for case_dto in unique_cases:
                try:
                    case_detail = case_service.get_case_detail_internal(cast(int, case_dto.id))

                    case_numbers: list[Any] = getattr(case_detail, "case_numbers", [])
                    parties: list[Any] = getattr(case_detail, "parties", [])

                    cases_data.append(
                        {
                            "id": cast(int, case_detail.id),
                            "name": case_detail.name,
                            "case_numbers": case_numbers if isinstance(case_numbers, list) else [],
                            "parties": parties if isinstance(parties, list) else [],
                            "created_at": (
                                cast(Any, case_detail.created_at).strftime("%Y-%m-%d %H:%M")
                                if cast(Any, case_detail.created_at)
                                else ""
                            ),
                        }
                    )
                except Exception as e:
                    logger.warning(f"格式化案件数据失败: Case ID={case_dto.id}, 错误: {e!s}")
                    continue

            return JsonResponse({"cases": cases_data})

        except Exception as e:
            logger.error(f"AJAX 搜索案件失败: SMS ID={sms_id}, 搜索词={search_term}, 错误: {e!s}")
            return JsonResponse({"error": "搜索失败,请重试"}, status=500)

    def retry_single_sms_view(self, request: HttpRequest, sms_id: int) -> HttpResponse:
        """单个短信重新处理"""
        get_object_or_404(CourtSMS, id=sms_id)

        try:
            service = _get_court_sms_service()
            service.retry_processing(sms_id)

            messages.success(request, f"短信 #{sms_id} 重新处理成功!")
            logger.info(f"管理员重新处理单个短信: SMS ID={sms_id}, User={request.user}")

        except Exception as e:
            messages.error(request, f"重新处理失败: {e!s}")
            logger.error(f"管理员重新处理单个短信失败: SMS ID={sms_id}, 错误: {e!s}")

        return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

    def save_model(self, request: HttpRequest, obj: CourtSMS, form: Any, change: bool) -> None:
        """保存模型时的处理"""
        if not change:
            if not obj.received_at:
                from django.utils import timezone

                obj.received_at = timezone.now()

            super().save_model(request, obj, form, change)  # type: ignore[misc]

            try:
                from django_q.tasks import async_task

                task_id = async_task(
                    "apps.automation.services.sms.court_sms_service.process_sms_async",
                    cast(int, obj.id),
                    task_name=f"court_sms_processing_{obj.id}",
                )

                messages.success(request, f"短信已保存并开始处理!记录ID: {obj.id}")
                logger.info(f"管理员添加短信并触发处理: SMS ID={obj.id}, Task ID={task_id}, User={request.user}")

            except Exception as e:
                messages.warning(request, f"短信已保存,但处理任务启动失败: {e!s}")
                logger.error(f"管理员添加短信后处理任务启动失败: SMS ID={obj.id}, 错误: {e!s}")
        else:
            super().save_model(request, obj, form, change)  # type: ignore[misc]
