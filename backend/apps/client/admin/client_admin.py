from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.automation.models.gsxt_report import GsxtReportTask
from apps.client.models import Client, ClientIdentityDoc
from apps.core.admin.mixins import AdminImportExportMixin

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.forms import ModelForm

logger = logging.getLogger("apps.client")


def _get_admin_service() -> Any:
    """工厂函数：创建 ClientAdminService 实例"""
    from apps.client.services import ClientAdminService

    return ClientAdminService()


class GsxtReportTaskInlineForm(forms.ModelForm[GsxtReportTask]):
    class Meta:
        model = GsxtReportTask
        fields: ClassVar = []

    class Media:
        css: ClassVar = {"all": ("automation/gsxt_inline.css",)}


class GsxtReportTaskInline(admin.TabularInline):  # type: ignore[type-arg]
    model = GsxtReportTask
    form = GsxtReportTaskInlineForm
    extra = 0
    can_delete = False
    fields: ClassVar = ("created_at", "status", "error_message", "inbox_link")
    readonly_fields: ClassVar = ("created_at", "status", "error_message", "inbox_link")
    ordering = ("-created_at",)
    verbose_name = _("企业信用报告任务")
    verbose_name_plural = _("企业信用报告任务")

    def inbox_link(self, obj: GsxtReportTask) -> str:
        from apps.automation.models.gsxt_report import GsxtReportStatus
        from apps.organization.models.credential import AccountCredential
        if obj.status != GsxtReportStatus.WAITING_EMAIL:
            return "—"
        cred = AccountCredential.objects.filter(pk=4).first()
        email = cred.account if cred else "huangsong94@163.com"
        return format_html('<a href="https://mail.163.com" target="_blank">📬 打开 {} 收件箱</a>', email)

    inbox_link.short_description = _("收件箱")  # type: ignore[attr-defined]

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:  # type: ignore[override]
        from apps.automation.models.gsxt_report import GsxtReportStatus
        from django.conf import settings

        instances = formset.save(commit=False)
        for f in formset.forms:
            uploaded = f.cleaned_data.get("report_upload") if f.cleaned_data else None
            if not uploaded:
                continue
            obj: GsxtReportTask = f.instance
            if not obj.pk:
                continue
            client = obj.client
            rel_path = f"client_docs/{client.pk}/{client.name[:20]}_企业信用报告.pdf"
            abs_path = Path(settings.MEDIA_ROOT) / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            with abs_path.open("wb") as fp:
                for chunk in uploaded.chunks():
                    fp.write(chunk)
            doc, _ = ClientIdentityDoc.objects.get_or_create(
                client=client, doc_type=ClientIdentityDoc.BUSINESS_LICENSE
            )
            doc.file_path = str(rel_path)
            doc.save(update_fields=["file_path"])
            obj.status = GsxtReportStatus.SUCCESS
            obj.error_message = ""
            obj.save(update_fields=["status", "error_message"])
        formset.save_m2m()


class ClientIdentityDocInlineForm(forms.ModelForm[ClientIdentityDoc]):
    upload = forms.FileField(required=False, label=_("上传文件"))

    class Meta:
        model = ClientIdentityDoc
        fields: ClassVar = ["doc_type", "upload"]


class ClientIdentityDocInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ClientIdentityDoc
    form = ClientIdentityDocInlineForm
    extra = 1
    fields: ClassVar = ("doc_type", "file_link", "upload")
    readonly_fields: ClassVar = ("file_link",)

    def file_link(self, obj: ClientIdentityDoc) -> str:
        url = obj.media_url
        if url:
            return format_html('<a href="{}" target="_blank">{}</a>', url, Path(obj.file_path or "").name)
        return ""

    file_link.short_description = _("文件")  # type: ignore[attr-defined]


class ClientAdminForm(forms.ModelForm[Client]):
    class Meta:
        model = Client
        fields = "__all__"

    class Media:
        css: ClassVar = {"all": ("client/admin.css",)}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        ct = None
        if self.instance and getattr(self.instance, "client_type", None):
            ct = self.instance.client_type
        elif "client_type" in self.data:
            ct = self.data.get("client_type")
        elif self.initial.get("client_type"):
            ct = self.initial.get("client_type")
        self.fields["id_number"].label = _("身份证号码") if ct == "natural" else _("统一社会信用代码")


def serialize_client_obj(obj: Any) -> dict[str, Any]:
    """将单个 Client 实例序列化为 dict（供 ClientAdmin、CaseAdmin、ContractAdmin 共用）。"""
    return {
        "name": obj.name,
        "client_type": obj.client_type,
        "id_number": obj.id_number,
        "phone": obj.phone,
        "address": getattr(obj, "address", None),
        "legal_representative": obj.legal_representative,
        "legal_representative_id_number": getattr(obj, "legal_representative_id_number", None),
        "is_our_client": obj.is_our_client,
        "identity_docs": [
            {"doc_type": doc.doc_type, "file_path": doc.file_path} for doc in obj.identity_docs.all() if doc.file_path
        ],
        "property_clues": [
            {
                "clue_type": clue.clue_type,
                "content": clue.content,
                "attachments": [
                    {"file_path": att.file_path, "file_name": att.file_name}
                    for att in clue.attachments.all()
                    if att.file_path
                ],
            }
            for clue in obj.property_clues.all()
        ],
    }


@admin.register(Client)
class ClientAdmin(AdminImportExportMixin, admin.ModelAdmin[Client]):
    list_display: ClassVar = ("id", "name", "client_type", "is_our_client", "phone", "legal_representative")
    search_fields: ClassVar = ("name", "phone", "id_number")
    list_filter: ClassVar = ("client_type", "is_our_client")
    form = ClientAdminForm
    inlines: ClassVar = []
    export_model_name = "client"
    import_required_fields = ("name",)
    actions: ClassVar = ["export_selected_as_json", "export_all_as_json"]

    def get_urls(self) -> list[Any]:
        from django.urls import path

        urls = super().get_urls()
        custom = [
            path(
                "<int:client_id>/fetch-gsxt-report/",
                self.admin_site.admin_view(self._fetch_gsxt_report_view),
                name="client_client_fetch_gsxt_report",
            ),
            path(
                "<int:client_id>/upload-gsxt-report/<int:task_id>/",
                self.admin_site.admin_view(self._upload_gsxt_report_view),
                name="client_client_upload_gsxt_report",
            ),
        ]
        return custom + urls

    def _fetch_gsxt_report_view(self, request: HttpRequest, client_id: int) -> Any:
        from django.shortcuts import redirect

        from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
        from apps.automation.services.gsxt.gsxt_login_service import GsxtLoginError, start_login_gsxt
        from apps.organization.models.credential import AccountCredential

        client = Client.objects.get(pk=client_id)

        if client.client_type != "legal":
            self.message_user(request, _("仅法人/非法人组织当事人支持获取企业信用报告"), messages.WARNING)
            return redirect(f"../../{client_id}/change/")

        credential = (
            AccountCredential.objects.filter(site_name="国家企业信用信息公示系统")
            .order_by("-is_preferred", "-last_login_success_at")
            .first()
        )
        if not credential:
            self.message_user(request, _("未找到国家企业信用信息公示系统账号，请先在账号密码管理中添加"), messages.ERROR)
            return redirect(f"../../{client_id}/change/")

        # 创建任务记录
        task = GsxtReportTask.objects.create(
            client=client,
            company_name=client.name,
            credit_code=client.id_number or "",
            status=GsxtReportStatus.WAITING_CAPTCHA,
        )

        # 非阻塞：启动 Chrome、填账号密码，立即返回
        try:
            start_login_gsxt(credential, task.id)
        except GsxtLoginError as e:
            task.status = GsxtReportStatus.FAILED
            task.error_message = str(e)
            task.save(update_fields=["status", "error_message"])
            self.message_user(request, str(e), messages.ERROR)
            return redirect(f"../../{client_id}/change/")

        self.message_user(
            request,
            _("Chrome 已打开登录页，请在浏览器中完成验证码，系统将自动继续后续流程"),
            messages.SUCCESS,
        )
        return redirect(f"../../{client_id}/change/")

    def _upload_gsxt_report_view(self, request: HttpRequest, client_id: int, task_id: int) -> Any:
        from django.shortcuts import redirect

        from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
        from django.conf import settings

        if request.method != "POST" or not request.FILES.get("report_file"):
            self.message_user(request, _("请选择 PDF 文件"), messages.WARNING)
            return redirect(f"../../{client_id}/change/")

        task = GsxtReportTask.objects.select_related("client").get(pk=task_id)
        client = task.client
        uploaded = request.FILES["report_file"]

        rel_path = f"client_docs/{client.pk}/{client.name[:20]}_企业信用报告.pdf"
        abs_path = Path(settings.MEDIA_ROOT) / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with abs_path.open("wb") as f:
            for chunk in uploaded.chunks():
                f.write(chunk)

        doc, _ = ClientIdentityDoc.objects.get_or_create(
            client=client,
            doc_type=ClientIdentityDoc.BUSINESS_LICENSE,
        )
        doc.file_path = str(rel_path)
        doc.save(update_fields=["file_path"])

        task.status = GsxtReportStatus.SUCCESS
        task.error_message = ""
        task.save(update_fields=["status", "error_message"])

        self.message_user(request, _("报告已上传并保存为营业执照附件"), messages.SUCCESS)
        return redirect(f"../../{client_id}/change/")

    def get_changeform_initial_data(self, request: HttpRequest) -> dict[str, Any]:
        return {"client_type": "legal"}

    def get_inlines(self, request: HttpRequest, obj: Client | None = None) -> list[type[Any]]:
        inlines = [ClientIdentityDocInline]
        if obj and obj.client_type == "legal":
            inlines.append(GsxtReportTaskInline)
        return inlines

    def save_formset(self, request: HttpRequest, form: ModelForm[Client], formset: Any, change: bool) -> None:
        # 收集需要处理的上传文件信息（在 save 之前）
        upload_info: list[dict[str, Any]] = []
        for f in formset.forms:
            if not f.cleaned_data:
                continue
            if f.cleaned_data.get("DELETE"):
                continue
            uploaded_file = f.cleaned_data.get("upload")
            if uploaded_file:
                upload_info.append(
                    {
                        "form": f,
                        "uploaded_file": uploaded_file,
                        "doc_type": f.cleaned_data.get("doc_type"),
                    }
                )

        # 调用父类 save，让 Django 处理保存和设置 new_objects 等属性
        formset.save()

        # 处理文件上传和重命名
        if upload_info:
            admin_service = _get_admin_service()
            client = form.instance

            for info in upload_info:
                instance = info["form"].instance
                if instance.pk:
                    admin_service.save_and_rename_file(
                        client_id=client.id,
                        client_name=client.name,
                        doc_id=instance.pk,
                        doc_type=info["doc_type"],
                        uploaded_file=info["uploaded_file"],
                    )

            # 如果上传了营业执照，把 WAITING_EMAIL 的报告任务标记为成功
            has_business_license = any(
                info["doc_type"] == ClientIdentityDoc.BUSINESS_LICENSE for info in upload_info
            )
            if has_business_license:
                from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
                GsxtReportTask.objects.filter(
                    client=form.instance,
                    status=GsxtReportStatus.WAITING_EMAIL,
                ).update(status=GsxtReportStatus.SUCCESS, error_message="")

    def handle_json_import(
        self, data_list: list[dict[str, Any]], user: str, zip_file: Any
    ) -> tuple[int, int, list[str]]:
        from apps.client.services.client_resolve_service import ClientResolveService

        svc = ClientResolveService()
        success = skipped = 0
        errors: list[str] = []
        for i, item in enumerate(data_list, 1):
            try:
                id_number = item.get("id_number")
                before = Client.objects.filter(id_number=id_number).exists() if id_number else False
                svc.resolve_with_attachments(item)
                if not before:
                    success += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.exception("导入客户失败", extra={"index": i, "client_name": item.get("name", "?")})
                errors.append(f"[{i}] {item.get('name', '?')} ({type(exc).__name__}): {exc}")
        return success, skipped, errors

    def serialize_queryset(self, queryset: QuerySet[Client]) -> list[dict[str, Any]]:
        result = []
        for obj in queryset.prefetch_related("identity_docs", "property_clues__attachments"):
            result.append(serialize_client_obj(obj))
        return result

    def get_file_paths(self, queryset: QuerySet[Client]) -> list[str]:  # type: ignore[override]
        paths = []
        for obj in queryset.prefetch_related("identity_docs", "property_clues__attachments"):
            for doc in obj.identity_docs.all():
                if doc.file_path:
                    paths.append(doc.file_path)
            for clue in obj.property_clues.all():
                for att in clue.attachments.all():
                    if att.file_path:
                        paths.append(att.file_path)
        return paths
