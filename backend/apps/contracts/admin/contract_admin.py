from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import Prefetch
from django.http import HttpRequest, JsonResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

from apps.contracts.admin.contract_inlines import (
    ContractAssignmentInline,
    ContractPartyInline,
    FinalizedMaterialInline,
    SupplementaryAgreementInline,
)
from apps.contracts.admin.mixins.action_mixin import ContractActionMixin
from apps.contracts.admin.mixins.display_mixin import ContractDisplayMixin
from apps.contracts.admin.mixins.save_mixin import ContractSaveMixin
from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractFinanceLog,
    ContractParty,
    ContractStatus,
    FinalizedMaterial,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.core.admin.mixins import AdminImportExportMixin
from apps.core.models.enums import CaseStage
from simple_history.admin import SimpleHistoryAdmin

from apps.cases.models import Case, CaseAssignment as CaseAssignmentModel, CaseLog, CaseParty
from apps.client.models import Client

# --- Prefetch 优化：共享 Client queryset，避免重复查询 ---
_client_with_nested = Client.objects.prefetch_related("identity_docs", "property_clues__attachments")

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
    from django.db.models import QuerySet
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
    except ImportError:
        BaseModelAdmin = admin.ModelAdmin


def serialize_contract_obj(obj: Any) -> dict[str, Any]:
    """将单个 Contract 实例序列化为 dict（供 ContractAdmin 和 CaseAdmin 共用）。"""
    from apps.contracts.services.contract.integrations import serialize_contract_obj as serialize_contract_obj_service

    result: dict[str, Any] = serialize_contract_obj_service(obj)
    return result


@admin.register(Contract)
class ContractAdmin(
    ContractDisplayMixin, ContractSaveMixin, ContractActionMixin, AdminImportExportMixin, SimpleHistoryAdmin, BaseModelAdmin
):
    class ContractAdminForm(forms.ModelForm[Contract]):
        representation_stages = forms.MultipleChoiceField(
            choices=CaseStage.choices,
            required=False,
            widget=forms.SelectMultiple,
            label=_("代理阶段"),
        )

        class Meta:
            model = Contract
            fields = "__all__"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            if not getattr(self.instance, "pk", None):
                self.fields["status"].initial = ContractStatus.ACTIVE
                self.fields["specified_date"].initial = timezone.localdate()
            self.fields["representation_stages"].initial = list(
                getattr(self.instance, "representation_stages", []) or []
            )

        def clean(self) -> dict[str, Any]:
            cleaned = super().clean() or {}
            try:
                from apps.contracts.validators import normalize_representation_stages

                ctype = cleaned.get("case_type")
                rep = cleaned.get("representation_stages") or []
                cleaned["representation_stages"] = normalize_representation_stages(ctype, rep, strict=False)
            except Exception:
                logger.exception("操作失败")
            return cleaned

    form = ContractAdminForm
    list_display = (
        "id",
        "name_link",
        "case_type",
        "status",
        "get_primary_lawyer",
        "fee_mode",
        "fixed_amount",
        "risk_rate",
    )
    list_filter = ("case_type", "status", "fee_mode", "is_filed", ("specified_date", admin.DateFieldListFilter))
    search_fields = ("name", "filing_number", "contract_parties__client__name")
    date_hierarchy = "specified_date"
    readonly_fields = ("get_primary_lawyer_display", "filing_number", "get_matched_template_display", "get_matched_folder_templates_display")
    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": ("name", "case_type", "status", "specified_date", "start_date", "end_date"),
            },
        ),
        (
            _("收费信息"),
            {
                "fields": ("fee_mode", "fixed_amount", "risk_rate", "custom_terms"),
            },
        ),
        (
            _("建档信息"),
            {
                "fields": ("is_filed", "filing_number"),
                "classes": ("collapse",),
            },
        ),
        (
            _("代理阶段"),
            {
                "fields": ("representation_stages",),
                "classes": ("collapse",),
            },
        ),
        (
            _("律所OA信息"),
            {
                "fields": ("law_firm_oa_url", "law_firm_oa_case_number"),
                "classes": ("collapse",),
            },
        ),
        (
            _("归档设置"),
            {
                "fields": ("compact_archive",),
                "classes": ("collapse",),
            },
        ),
    )
    export_model_name = "contract"
    import_required_fields = ("name",)
    actions = ["export_selected_as_json", "export_all_as_json", "archive_selected_contracts", "file_selected_contracts"]

    inlines: ClassVar = [
        ContractPartyInline,
        ContractAssignmentInline,
        SupplementaryAgreementInline,
        FinalizedMaterialInline,
    ]

    class Media:
        js = ("cases/admin_case_form.js",)

    change_form_template = "admin/contracts/contract/change_form.html"
    change_list_template = "admin/contracts/contract/change_list.html"

    @admin.action(description=_("批量归档选中合同"))
    def archive_selected_contracts(self, request: HttpRequest, queryset: Any) -> None:
        from apps.core.interfaces import ServiceLocator

        case_service = ServiceLocator.get_case_service()
        updated = 0
        for contract in queryset.exclude(status=ContractStatus.ARCHIVED):
            contract.status = ContractStatus.ARCHIVED
            contract.save(update_fields=["status"])
            closed = case_service.close_cases_by_contract_internal(contract.id)
            if closed:
                logger.info("批量归档: 合同 %s 自动结案 %d 个关联案件", contract.id, closed)
            updated += 1
        self.message_user(request, _("已归档 %(count)d 个合同") % {"count": updated})

    @admin.action(description=_("批量建档选中合同"))
    def file_selected_contracts(self, request: HttpRequest, queryset: Any) -> None:
        from apps.contracts.admin.wiring_admin import get_contract_admin_service

        service = get_contract_admin_service()
        updated = 0
        for contract in queryset.filter(is_filed=False):
            filing_number = service.handle_contract_filing_change(contract_id=contract.id, is_filed=True)
            if filing_number:
                contract.filing_number = filing_number
                contract.is_filed = True
                contract.save(update_fields=["is_filed", "filing_number"])
                updated += 1
        self.message_user(request, _("已建档 %(count)d 个合同") % {"count": updated})

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> Any:
        from django.http import HttpResponseRedirect

        if "status__exact" not in request.GET:
            return HttpResponseRedirect(f"{request.path}?status__exact=active")
        # 保存筛选状态到 session，供详情页"返回列表"使用
        if request.GET:
            request.session["contract_changelist_filters"] = request.GET.urlencode()
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).prefetch_related("assignments__lawyer")

    def get_urls(self) -> list[Any]:
        from django.urls import path as urlpath

        urls = super().get_urls()
        custom = [
            urlpath(
                "batch-folder-binding/",
                self.admin_site.admin_view(self.batch_folder_binding_view),
                name="contracts_contract_batch_folder_binding",
            ),
            urlpath(
                "batch-folder-binding/preview/",
                self.admin_site.admin_view(self.batch_folder_binding_preview_view),
                name="contracts_contract_batch_folder_binding_preview",
            ),
            urlpath(
                "batch-folder-binding/save/",
                self.admin_site.admin_view(self.batch_folder_binding_save_view),
                name="contracts_contract_batch_folder_binding_save",
            ),
            urlpath(
                "batch-folder-binding/open-folder/",
                self.admin_site.admin_view(self.batch_folder_binding_open_folder_view),
                name="contracts_contract_batch_folder_binding_open_folder",
            ),
            urlpath(
                "<int:contract_id>/reorder-materials/",
                self.admin_site.admin_view(self.reorder_materials_view),
                name="contracts_contract_reorder_materials",
            ),
            urlpath(
                "oa-sync/",
                self.admin_site.admin_view(self.oa_sync_view),
                name="contracts_contract_oa_sync",
            ),
            urlpath(
                "oa-sync/start/",
                self.admin_site.admin_view(self.oa_sync_start_view),
                name="contracts_contract_oa_sync_start",
            ),
            urlpath(
                "oa-sync/status/<int:session_id>/",
                self.admin_site.admin_view(self.oa_sync_status_view),
                name="contracts_contract_oa_sync_status",
            ),
            urlpath(
                "oa-sync/save/",
                self.admin_site.admin_view(self.oa_sync_save_view),
                name="contracts_contract_oa_sync_save",
            ),
            urlpath(
                "jtn-oa-import/",
                self.admin_site.admin_view(self.jtn_oa_import_view),
                name="contracts_contract_jtn_oa_import",
            ),
        ]
        return custom + urls  # type: ignore[no-any-return]

    def reorder_materials_view(self, request: HttpRequest, contract_id: int) -> Any:
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"error": "Permission denied"}, status=403)
        try:
            data = json.loads(request.body)
            ids: list[int] = data.get("ids", [])
            for i, pk in enumerate(ids):
                FinalizedMaterial.objects.filter(pk=pk, contract_id=contract_id).update(order=i)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    def batch_folder_binding_view(self, request: HttpRequest) -> TemplateResponse:
        if not self.has_view_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        service = get_contract_batch_folder_binding_service()
        context = self.admin_site.each_context(request)
        context.update(
            {
                "title": _("合同批量绑定文件夹"),
                "opts": self.model._meta,
                "cards": service.list_unbound_case_type_cards(),
                "batch_folder_binding_config": {
                    "previewUrl": "/admin/contracts/contract/batch-folder-binding/preview/",
                    "saveUrl": "/admin/contracts/contract/batch-folder-binding/save/",
                    "openFolderUrl": "/admin/contracts/contract/batch-folder-binding/open-folder/",
                    "changeListUrl": "/admin/contracts/contract/",
                },
            }
        )
        return TemplateResponse(request, "admin/contracts/contract/batch_folder_binding.html", context)

    def oa_sync_view(self, request: HttpRequest) -> TemplateResponse:
        if not self.has_view_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        service = get_contract_oa_sync_service()
        context = self.admin_site.each_context(request)
        context.update(
            {
                "title": _("合同OA信息同步"),
                "opts": self.model._meta,
                "oa_sync_initial_contracts": service.list_missing_oa_contracts(),
                "oa_sync_config": {
                    "startUrl": "/admin/contracts/contract/oa-sync/start/",
                    "statusUrl": "/admin/contracts/contract/oa-sync/status/__SESSION_ID__/",
                    "saveUrl": "/admin/contracts/contract/oa-sync/save/",
                    "changeListUrl": "/admin/contracts/contract/",
                },
            }
        )
        return TemplateResponse(request, "admin/contracts/contract/oa_sync.html", context)

    def jtn_oa_import_view(self, request: HttpRequest) -> TemplateResponse:
        """金诚同达OA导入独立页面 - 与列表页解耦，方便未来替换为其他律所OA"""
        if not self.has_change_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        context = self.admin_site.each_context(request)
        context.update(
            {
                "title": _("从金诚同达OA导入案件"),
                "opts": self.model._meta,
            }
        )
        return TemplateResponse(request, "admin/contracts/contract/jtn_oa_import.html", context)

    def oa_sync_start_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        try:
            service = get_contract_oa_sync_service()
            session = service.create_or_get_active_session(started_by=request.user)
            session = service.submit_session_task(session=session)
            return JsonResponse(
                {
                    "success": True,
                    "message": _("同步任务已启动"),
                    "session_id": int(session.id),
                }
            )
        except Exception as exc:
            logger.exception("contract_oa_sync_start_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def oa_sync_save_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        payload = self._parse_json_payload(request)
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        try:
            result = get_contract_oa_sync_service().save_manual_contract_oa_fields(updates=entries)
            message = _("保存成功") if result.get("error_count", 0) == 0 else _("部分保存成功，请检查错误项")
            return JsonResponse({"success": True, "message": message, **result})
        except Exception as exc:
            logger.exception("contract_oa_sync_save_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def oa_sync_status_view(self, request: HttpRequest, session_id: int) -> JsonResponse:
        if request.method != "GET":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_view_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_oa_sync_service

        service = get_contract_oa_sync_service()
        session = service.get_session(session_id=session_id)
        if session is None:
            return JsonResponse({"success": False, "message": _("会话不存在")}, status=404)

        return JsonResponse({"success": True, **service.build_status_payload(session=session)})

    def batch_folder_binding_preview_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        payload = self._parse_json_payload(request)
        case_type_roots = payload.get("case_type_roots")
        if not isinstance(case_type_roots, list):
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        try:
            data = get_contract_batch_folder_binding_service().preview(case_type_roots=case_type_roots)
            return JsonResponse({"success": True, **data})
        except Exception as exc:
            logger.exception("contract_batch_folder_binding_preview_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def batch_folder_binding_save_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        payload = self._parse_json_payload(request)
        case_type_roots = payload.get("case_type_roots")
        contract_selections = payload.get("contract_selections")
        if not isinstance(case_type_roots, list) or not isinstance(contract_selections, list):
            return JsonResponse({"success": False, "message": _("参数格式错误")}, status=400)

        try:
            result = get_contract_batch_folder_binding_service().save(
                case_type_roots=case_type_roots,
                contract_selections=contract_selections,
            )
            return JsonResponse({"success": True, **result})
        except Exception as exc:
            logger.exception("contract_batch_folder_binding_save_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def batch_folder_binding_open_folder_view(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({"success": False, "message": _("Permission denied")}, status=403)

        from apps.contracts.admin.wiring_admin import get_contract_batch_folder_binding_service

        payload = self._parse_json_payload(request)
        root_path = str(payload.get("root_path") or "").strip()
        folder_path = str(payload.get("folder_path") or "").strip()
        if not root_path or not folder_path:
            return JsonResponse({"success": False, "message": _("缺少路径参数")}, status=400)

        try:
            get_contract_batch_folder_binding_service().open_folder(root_path=root_path, folder_path=folder_path)
            return JsonResponse({"success": True, "message": _("已打开文件夹")})
        except Exception as exc:
            logger.exception("contract_batch_folder_binding_open_folder_failed")
            return JsonResponse({"success": False, "message": str(exc)}, status=400)

    def _parse_json_payload(self, request: HttpRequest) -> dict[str, Any]:
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def handle_json_import(
        self, data_list: list[dict[str, Any]], user: str, zip_file: Any
    ) -> tuple[int, int, list[str]]:
        from apps.contracts.services.contract_import_service import build_contract_import_service_for_admin

        contract_svc = build_contract_import_service_for_admin()

        success = skipped = 0
        errors: list[str] = []
        for i, item in enumerate(data_list, 1):
            try:
                filing_number = item.get("filing_number")
                before = Contract.objects.filter(filing_number=filing_number).exists() if filing_number else False
                contract_svc.resolve(item)  # type: ignore[arg-type]
                if before:
                    skipped += 1
                else:
                    success += 1
            except Exception as exc:
                logger.exception("导入合同失败", extra={"index": i, "contract_name": item.get("name", "?")})
                errors.append(f"[{i}] {item.get('name', '?')} ({type(exc).__name__}): {exc}")
        return success, skipped, errors

    def serialize_queryset(self, queryset: QuerySet[Contract]) -> list[dict[str, Any]]:
        result = []
        for obj in queryset.prefetch_related(
            # 合同当事人 + 客户（含证件、财产线索）
            Prefetch(
                "contract_parties",
                queryset=ContractParty.objects.prefetch_related(
                    Prefetch("client", queryset=_client_with_nested),
                ),
            ),
            # 律师指派（FK → select_related 减少查询）
            Prefetch("assignments", queryset=ContractAssignment.objects.select_related("lawyer")),
            "finalized_materials",
            # 补充协议 + 当事人
            Prefetch(
                "supplementary_agreements",
                queryset=SupplementaryAgreement.objects.prefetch_related(
                    Prefetch("parties", queryset=SupplementaryAgreementParty.objects.prefetch_related(
                        Prefetch("client", queryset=_client_with_nested),
                    )),
                ),
            ),
            "payments__invoices",
            # 财务日志（FK → select_related）
            Prefetch("finance_logs", queryset=ContractFinanceLog.objects.select_related("actor")),
            "client_payment_records",
            # 案件（嵌套 prefetch）
            Prefetch(
                "cases",
                queryset=Case.objects.prefetch_related(
                    Prefetch(
                        "parties",
                        queryset=CaseParty.objects.prefetch_related(
                            Prefetch("client", queryset=_client_with_nested),
                        ),
                    ),
                    Prefetch("assignments", queryset=CaseAssignmentModel.objects.select_related("lawyer")),
                    "supervising_authorities",
                    "case_numbers",
                    "chats",
                    Prefetch(
                        "logs",
                        queryset=CaseLog.objects.select_related("actor").prefetch_related("attachments"),
                    ),
                ),
            ),
        ):
            result.append(serialize_contract_obj(obj))
        return result

    def get_file_paths(self, queryset: QuerySet[Contract]) -> list[str]:
        seen: set[str] = set()
        paths: list[str] = []

        def _add(p: str) -> None:
            if p and p not in seen:
                seen.add(p)
                paths.append(p)

        for obj in queryset.prefetch_related(
            "finalized_materials",
            "client_payment_records",
            "payments__invoices",
            # 合同当事人 + 客户（含证件、财产线索），共享 Client queryset
            Prefetch(
                "contract_parties",
                queryset=ContractParty.objects.prefetch_related(
                    Prefetch("client", queryset=_client_with_nested),
                ),
            ),
        ):
            for m in obj.finalized_materials.all():
                _add(m.file_path)
            for r in obj.client_payment_records.all():
                _add(r.image_path)  # type: ignore[arg-type]
            for p in obj.payments.all():
                for inv in p.invoices.all():
                    _add(inv.file_path)
            for p in obj.contract_parties.all():
                for d in p.client.identity_docs.all():
                    _add(d.file_path)
                for c in p.client.property_clues.all():
                    for a in c.attachments.all():
                        _add(a.file_path)
        return paths
