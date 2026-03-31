"""
法院短信 Admin 自定义视图方法

提供短信提交、案件指定、重试处理等视图功能.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.automation.services.admin import CourtSMSAdminService

logger = logging.getLogger("apps.automation")


def _get_court_sms_service() -> Any:
    """获取法院短信服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_court_sms_service()


def _get_case_service() -> Any:
    """获取案件服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_case_service()


def _get_admin_service() -> CourtSMSAdminService:
    """获取 Admin 服务实例(工厂函数)"""
    return CourtSMSAdminService()


class CourtSMSViewsMixin:
    """
    法院短信 Admin 视图方法混入类

    提供所有自定义视图方法的实现.
    """

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

        admin_service = _get_admin_service()
        recent_sms = admin_service.get_recent_sms(limit=10)

        context: dict[str, Any] = {
            "title": "提交法院短信",
            "recent_sms": recent_sms,
            "opts": self.model._meta,  # type: ignore[attr-defined]
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/submit_sms.html", context)

    def assign_case_view(self, request: HttpRequest, sms_id: int) -> HttpResponse:
        """手动指定案件页面"""
        admin_service = _get_admin_service()
        sms = admin_service.get_sms_by_id(sms_id)

        if request.method == "POST":
            case_id = request.POST.get("case_id")

            if not case_id:
                messages.error(request, "请选择一个案件")
            else:
                try:
                    admin_service.assign_case(sms_id, int(case_id))

                    messages.success(request, "案件指定成功!已触发文书重命名和推送通知流程")
                    logger.info(f"管理员手动指定案件: SMS ID={sms_id}, Case ID={case_id}, User={request.user}")

                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

                except Exception as e:
                    messages.error(request, f"指定案件失败: {e!s}")
                    logger.error(f"管理员手动指定案件失败: SMS ID={sms_id}, Case ID={case_id}, 错误: {e!s}")

        case_service = _get_case_service()

        suggested_cases = self._get_suggested_cases(sms, case_service, sms_id)
        recent_cases = self._get_recent_cases(case_service, sms_id)

        formatted_suggested = [self._format_case_for_template(c) for c in (suggested_cases or [])]
        formatted_recent = [self._format_case_for_template(c) for c in (recent_cases or [])]

        context: dict[str, Any] = {
            "title": f"为短信 #{sms_id} 指定案件",
            "sms": sms,
            "suggested_cases": formatted_suggested,
            "recent_cases": formatted_recent,
            "opts": self.model._meta,  # type: ignore[attr-defined]
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/assign_case.html", context)

    def _get_suggested_cases(self, sms: Any, case_service: Any, sms_id: int) -> list[Any]:
        """获取推荐案件列表"""
        suggested_cases: list[Any] = []
        from apps.core.models.enums import CaseStatus

        try:
            if sms.party_names:
                for party_name in sms.party_names:
                    if party_name.strip():
                        cases: list[Any] = case_service.search_cases_by_party_internal(
                            [party_name.strip()], status=CaseStatus.ACTIVE
                        )[:5]
                        suggested_cases.extend(cases)

            if sms.case_numbers:
                for case_number in sms.case_numbers:
                    if case_number.strip():
                        number_cases: list[Any] = case_service.search_cases_by_case_number_internal(
                            case_number.strip()
                        )[:5]
                        suggested_cases.extend(number_cases)

            seen_ids: set[int] = set()
            unique_suggested_cases: list[Any] = []
            for case in suggested_cases:
                if hasattr(case, "id") and cast(int, case.id) not in seen_ids:
                    seen_ids.add(cast(int, case.id))
                    unique_suggested_cases.append(case)

            return unique_suggested_cases[:10]

        except Exception as e:
            logger.warning(f"获取推荐案件失败: SMS ID={sms_id}, 错误: {e!s}")
            return []

    def _get_recent_cases(self, case_service: Any, sms_id: int) -> list[Any]:
        """获取最近案件列表"""
        from apps.core.models.enums import CaseStatus

        try:
            result: list[Any] = case_service.list_cases_internal(status=CaseStatus.ACTIVE, limit=20)
            return result
        except Exception as e:
            logger.warning(f"获取最近案件失败: SMS ID={sms_id}, 错误: {e!s}")
            return []

    def _format_case_for_template(self, case_dto: Any) -> dict[str, Any]:
        """将 CaseDTO 转换为模板可用的格式"""
        try:
            case_service = _get_case_service()
            case_numbers: list[Any] = case_service.get_case_numbers_by_case_internal(cast(int, case_dto.id))
            parties: list[Any] = case_service.get_case_party_names_internal(cast(int, case_dto.id))

            return {
                "id": cast(int, case_dto.id),
                "name": case_dto.name,
                "start_date": getattr(case_dto, "start_date", None),
                "case_numbers": case_numbers,
                "parties": parties,
            }
        except Exception as e:
            logger.warning(f"格式化案件数据失败: Case ID={case_dto.id}, 错误: {e!s}")
            return {
                "id": cast(int, case_dto.id),
                "name": case_dto.name,
                "start_date": getattr(case_dto, "start_date", None),
                "case_numbers": [],
                "parties": [],
            }

    def search_cases_ajax(self, request: HttpRequest, sms_id: int) -> JsonResponse:
        """AJAX 案件搜索接口"""
        if request.method != "GET":
            return JsonResponse({"error": "只支持 GET 请求"}, status=405)

        search_term = request.GET.get("q", "").strip()
        if not search_term:
            try:
                from apps.core.models.enums import CaseStatus

                case_service = _get_case_service()
                found_cases: list[Any] = case_service.list_cases_internal(status=CaseStatus.ACTIVE, limit=50)
                cases_data = self._format_cases_for_json(found_cases)
                return JsonResponse({"cases": cases_data})
            except Exception:
                logger.exception("操作失败")
                return JsonResponse({"cases": []})

        try:
            case_service = _get_case_service()
            found_cases = self._search_cases(case_service, search_term)
            cases_data = self._format_cases_for_json(found_cases)
            return JsonResponse({"cases": cases_data})

        except Exception as e:
            logger.error(f"AJAX 搜索案件失败: SMS ID={sms_id}, 搜索词={search_term}, 错误: {e!s}")
            return JsonResponse({"error": "搜索失败,请重试"}, status=500)

    def _search_cases(self, case_service: Any, search_term: str) -> list[Any]:
        """搜索案件并去重"""
        from apps.core.models.enums import CaseStatus

        result: list[Any] = case_service.search_cases_internal(search_term, status=CaseStatus.ACTIVE, limit=30)
        return result

    def _format_cases_for_json(self, cases: list[Any]) -> list[dict[str, Any]]:
        """将案件列表格式化为 JSON 格式"""
        cases_data: list[dict[str, Any]] = []
        case_service = _get_case_service()

        for case_dto in cases:
            try:
                case_numbers: list[Any] = case_service.get_case_numbers_by_case_internal(cast(int, case_dto.id))
                parties: list[Any] = case_service.get_case_party_names_internal(cast(int, case_dto.id))

                cases_data.append(
                    {
                        "id": cast(int, case_dto.id),
                        "name": case_dto.name,
                        "case_numbers": case_numbers if isinstance(case_numbers, list) else [],
                        "parties": parties if isinstance(parties, list) else [],
                        "created_at": getattr(case_dto, "start_date", "") or "",
                    }
                )
            except Exception as e:
                logger.warning(f"格式化案件数据失败: Case ID={case_dto.id}, 错误: {e!s}")
                continue

        return cases_data

    def retry_single_sms_view(self, request: HttpRequest, sms_id: int) -> HttpResponse:
        """单个短信重新处理"""
        admin_service = _get_admin_service()
        admin_service.get_sms_by_id(sms_id)

        try:
            admin_service.retry_processing(sms_id)

            messages.success(request, f"短信 #{sms_id} 重新处理成功!")
            logger.info(f"管理员重新处理单个短信: SMS ID={sms_id}, User={request.user}")

        except Exception as e:
            messages.error(request, f"重新处理失败: {e!s}")
            logger.error(f"管理员重新处理单个短信失败: SMS ID={sms_id}, 错误: {e!s}")

        return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))
