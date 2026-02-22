"""
Contract Admin - Action Mixin

操作处理方法:生成文档、复制合同、创建案件等.
"""

import logging
import urllib.parse
from typing import Any

from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.core.security import get_request_access_context

logger = logging.getLogger("apps.contracts")


def _get_contract_admin_service() -> Any:
    """工厂函数获取合同 Admin 服务"""
    from apps.contracts.admin.wiring_admin import get_contract_admin_service

    return get_contract_admin_service()


def _get_contract_mutation_facade() -> Any:
    from apps.contracts.admin.wiring_admin import get_contract_mutation_facade

    return get_contract_mutation_facade()


class ContractActionMixin:
    """合同 Admin 操作处理方法的 Mixin"""

    def response_change(self, request, obj) -> Any:
        """处理保存并复制、保存并创建案件、生成合同、生成补充协议、续签常法按钮"""
        _ACTION_HANDLERS = {
            "_generate_contract": self._handle_generate_contract,
            "_generate_supplementary_agreement": self._handle_generate_supplementary,
            "_renew_advisor": self._handle_renew_advisor,
            "_save_and_duplicate": self._handle_duplicate,
            "_save_and_create_case": self._handle_create_case,
        }
        for key, handler in _ACTION_HANDLERS.items():
            if key in request.POST:
                return handler(request, obj)

        # 普通保存操作:返回详情页而非列表页
        if "_continue" in request.POST or "_addanother" in request.POST:
            return super().response_change(request, obj)
        messages.success(request, f"合同「{obj.name}」已保存")
        return HttpResponseRedirect(reverse("admin:contracts_contract_detail", args=[obj.pk]))

    def _handle_generate_contract(self, request, obj) -> Any:
        try:
            service = _get_contract_admin_service()
            result = service.generate_contract_document(obj.pk)
            if result.get("folder_path"):
                messages.success(request, f"合同文档已生成并保存到: {result['folder_path']}")
                return HttpResponseRedirect(request.path)
            return self._build_docx_response(result)
        except (NotFoundError, ValidationException, PermissionDenied, RuntimeError) as e:
            logger.exception("操作失败")
            messages.error(request, f"生成合同失败: {e!s}")
            return HttpResponseRedirect(request.path)

    def _handle_generate_supplementary(self, request, obj) -> Any:
        try:
            agreement_id = request.POST.get("selected_agreement_id")
            if not agreement_id:
                messages.error(request, "请选择要生成的补充协议")
                return HttpResponseRedirect(request.path)
            service = _get_contract_admin_service()
            result = service.generate_supplementary_agreement(obj.pk, int(agreement_id))
            if result.get("folder_path"):
                messages.success(request, f"补充协议已生成并保存到: {result['folder_path']}")
                return HttpResponseRedirect(request.path)
            return self._build_docx_response(result)
        except (NotFoundError, ValidationException, PermissionDenied, RuntimeError) as e:
            logger.exception("操作失败")
            messages.error(request, f"生成补充协议失败: {e!s}")
            return HttpResponseRedirect(request.path)

    def _handle_renew_advisor(self, request, obj) -> Any:
        try:
            facade = _get_contract_mutation_facade()
            ctx = get_request_access_context(request)
            new_contract = facade.renew_advisor_contract_ctx(contract_id=obj.pk, ctx=ctx)
            messages.success(request, f"续签成功!已创建新合同,正在编辑新合同: {new_contract.name}")
            return HttpResponseRedirect(reverse("admin:contracts_contract_change", args=[new_contract.pk]))
        except (NotFoundError, ValidationException, PermissionDenied, RuntimeError) as e:
            logger.exception("操作失败")
            messages.error(request, f"续签失败: {e!s}")
            return HttpResponseRedirect(request.path)

    def _handle_duplicate(self, request, obj) -> Any:
        try:
            facade = _get_contract_mutation_facade()
            ctx = get_request_access_context(request)
            new_contract = facade.duplicate_contract_ctx(contract_id=obj.pk, ctx=ctx)
            messages.success(request, f"已复制合同,正在编辑新合同: {new_contract.name}")
            return HttpResponseRedirect(reverse("admin:contracts_contract_change", args=[new_contract.pk]))
        except (NotFoundError, ValidationException, PermissionDenied, RuntimeError) as e:
            logger.exception("操作失败")
            messages.error(request, f"复制失败: {e!s}")
            return HttpResponseRedirect(request.path)

    def _handle_create_case(self, request, obj) -> Any:
        try:
            facade = _get_contract_mutation_facade()
            ctx = get_request_access_context(request)
            new_case = facade.create_case_from_contract_ctx(contract_id=obj.pk, ctx=ctx)
            messages.success(request, f"已创建案件: {new_case.name}")
            return HttpResponseRedirect(reverse("admin:cases_case_change", args=[new_case.id]))
        except (NotFoundError, ValidationException, PermissionDenied, RuntimeError) as e:
            logger.exception("操作失败")
            messages.error(request, f"创建案件失败: {e!s}")
            return HttpResponseRedirect(request.path)

    def _build_docx_response(self, result: Any) -> Any:
        response = HttpResponse(
            result["content"],
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        encoded_filename = urllib.parse.quote(result["filename"].encode("utf-8"))
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        return response

    def response_add(self, request, obj, post_url_continue=None) -> Any:
        """处理新建合同后的保存并创建案件按钮"""
        if "_save_and_create_case" in request.POST:
            try:
                facade = _get_contract_mutation_facade()
                ctx = get_request_access_context(request)
                new_case = facade.create_case_from_contract_ctx(contract_id=obj.pk, ctx=ctx)
                messages.success(request, f"已创建案件: {new_case.name}")
                return HttpResponseRedirect(reverse("admin:cases_case_change", args=[new_case.id]))
            except (NotFoundError, ValidationException, PermissionDenied, RuntimeError) as e:
                logger.exception("操作失败")
                messages.error(request, f"创建案件失败: {e!s}")
                return HttpResponseRedirect(reverse("admin:contracts_contract_change", args=[obj.pk]))

        return super().response_add(request, obj, post_url_continue)
