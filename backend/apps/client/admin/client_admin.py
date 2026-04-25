import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django import forms
from django.apps import apps as django_apps
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest, JsonResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.client.models import Client, ClientIdentityDoc
from apps.client.ports import CredentialPort, GsxtReportPort
from apps.client.services.client_export_serializer_service import serialize_client_obj
from apps.client.services.wiring import get_credential_port, get_gsxt_report_port
from apps.core.admin.mixins import AdminImportExportMixin
from simple_history.admin import SimpleHistoryAdmin

logger = logging.getLogger("apps.client")


def _get_admin_service() -> Any:
    """工厂函数：创建 ClientAdminService 实例"""
    from apps.client.services import ClientAdminService

    return ClientAdminService()


def _get_gsxt_report_task_model() -> type[Any]:
    """延迟获取 GsxtReportTask 模型。"""
    return django_apps.get_model("automation", "GsxtReportTask")


class GsxtReportTaskInlineForm(forms.ModelForm[Any]):  # type: ignore[misc]
    class Meta:
        model = None  # type: ignore[misc]
        fields: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # 动态设置 Meta.model
        if self._meta.model is None:
            self._meta.model = _get_gsxt_report_task_model()
        super().__init__(*args, **kwargs)

    class Media:
        css = {"all": ("automation/gsxt_inline.css",)}


class GsxtReportTaskInline(admin.TabularInline[Any]):  # type: ignore[type-arg]
    model = _get_gsxt_report_task_model()
    form = GsxtReportTaskInlineForm
    extra = 0
    can_delete = False
    fields = ("created_at", "status", "error_message", "inbox_link")  # type: ignore[assignment]
    readonly_fields = ("created_at", "status", "error_message", "inbox_link")  # type: ignore[assignment]
    ordering = ("-created_at",)
    verbose_name = _("企业信用报告任务")
    verbose_name_plural = _("企业信用报告任务")

    def get_model(self) -> type[Any]:  # type: ignore[override]
        """延迟获取模型。"""
        return _get_gsxt_report_task_model()

    def inbox_link(self, obj: Any) -> str:
        """收件箱链接，使用端口获取状态检查。"""
        gsxt_port: GsxtReportPort = get_gsxt_report_port()
        credential_port: CredentialPort = get_credential_port()

        # 获取状态选项用于比较
        status_choices = gsxt_port.get_task_status_choices()
        waiting_email_value = next(
            (v for v, label in status_choices if "waiting_email" in v),
            "waiting_email",
        )

        if obj.status != waiting_email_value:
            return "—"

        credential = credential_port.get_gsxt_credential()
        email = credential.account if credential else "huangsong94@163.com"
        return format_html(
            '<a href="https://mail.163.com" target="_blank">📬 打开 {} 收件箱</a>',
            email,
        )

    inbox_link.short_description = _("收件箱")  # type: ignore[attr-defined]

    def save_formset(
        self,
        request: HttpRequest,
        form: Any,
        formset: Any,
        change: bool,
    ) -> None:
        """保存表单集，使用端口处理报告上传。"""
        from django.conf import settings

        instances = formset.save(commit=False)
        gsxt_port: GsxtReportPort = get_gsxt_report_port()

        for f in formset.forms:
            uploaded = f.cleaned_data.get("report_upload") if f.cleaned_data else None
            if not uploaded:
                continue
            obj: Any = f.instance
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
                client=client,
                doc_type=ClientIdentityDoc.BUSINESS_LICENSE,
            )
            doc.file_path = str(rel_path)
            doc.save(update_fields=["file_path"])
            # 使用端口标记任务成功
            gsxt_port.upload_report(
                task_id=obj.pk,
                file_content=b"",  # 文件已保存到本地，这里不传内容
                file_name=rel_path,
            )
        formset.save_m2m()


class ClientIdentityDocInlineForm(forms.ModelForm[ClientIdentityDoc]):
    upload = forms.FileField(required=False, label=_("上传文件"))

    class Meta:
        model = ClientIdentityDoc
        fields = ["doc_type", "upload"]


class ClientIdentityDocInline(admin.TabularInline[ClientIdentityDoc]):  # type: ignore[type-arg]
    model = ClientIdentityDoc
    form = ClientIdentityDocInlineForm
    extra = 1
    fields = ("doc_type", "file_link", "upload")  # type: ignore[assignment]
    readonly_fields = ("file_link",)  # type: ignore[assignment]

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
        css = {"all": ("client/admin.css",)}
        js = ("admin/js/jquery.init.js", "client/admin.js")

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


@admin.register(Client)
class ClientAdmin(SimpleHistoryAdmin, AdminImportExportMixin, admin.ModelAdmin[Client]):
    list_display = ("id", "name", "client_type", "is_our_client", "phone", "legal_representative")  # type: ignore[assignment]
    search_fields = ("name", "phone", "id_number")  # type: ignore[assignment]
    list_filter = ("client_type", "is_our_client")  # type: ignore[assignment]
    ordering = ("-pk",)  # type: ignore[assignment]
    form = ClientAdminForm
    inlines: list[type[Any]] = []  # type: ignore[assignment,misc]
    export_model_name = "client"
    import_required_fields = ("name",)
    actions = ["export_selected_as_json", "export_all_as_json"]  # type: ignore[assignment]

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
            path(
                "check-oa-credential/",
                self.admin_site.admin_view(self._check_oa_credential_view),
                name="client_client_check_oa_credential",
            ),
        ]
        return custom + urls

    def _fetch_gsxt_report_view(self, request: HttpRequest, client_id: int) -> Any:
        """获取企业信用报告视图。"""
        from django.shortcuts import redirect

        from apps.automation.services.gsxt.gsxt_login_service import GsxtLoginError

        client = Client.objects.get(pk=client_id)

        if client.client_type != "legal":
            self.message_user(
                request,
                _("仅法人/非法人组织当事人支持获取企业信用报告"),
                messages.WARNING,
            )
            return redirect(f"../../{client_id}/change/")

        # 使用端口获取凭证
        credential_port: CredentialPort = get_credential_port()
        credential = credential_port.get_gsxt_credential()

        if not credential:
            self.message_user(
                request,
                _("未找到国家企业信用信息公示系统账号，请先在账号密码管理中添加"),
                messages.ERROR,
            )
            return redirect(f"../../{client_id}/change/")

        # 使用端口创建任务
        gsxt_port: GsxtReportPort = get_gsxt_report_port()
        try:
            task_id = gsxt_port.create_report_task(
                client_id=client.id,
                company_name=client.name,
                credit_code=client.id_number or "",
            )

            # 非阻塞：启动 Chrome、填账号密码，立即返回
            gsxt_port.start_login(
                credential_id=credential.id,
                task_id=task_id,
            )
        except GsxtLoginError as e:
            self.message_user(request, str(e), messages.ERROR)
            return redirect(f"../../{client_id}/change/")

        self.message_user(
            request,
            _("Chrome 已打开登录页，请在浏览器中完成验证码，系统将自动继续后续流程"),
            messages.SUCCESS,
        )
        return redirect(f"../../{client_id}/change/")

    def _upload_gsxt_report_view(
        self,
        request: HttpRequest,
        client_id: int,
        task_id: int,
    ) -> Any:
        """上传企业信用报告视图。"""
        from django.conf import settings
        from django.shortcuts import redirect

        if request.method != "POST" or not request.FILES.get("report_file"):
            self.message_user(request, _("请选择 PDF 文件"), messages.WARNING)
            return redirect(f"../../{client_id}/change/")

        # 使用端口获取任务
        gsxt_port: GsxtReportPort = get_gsxt_report_port()
        task = gsxt_port.get_waiting_email_task(client_id=client_id)

        if not task or task.id != task_id:
            self.message_user(request, _("任务不存在或状态不正确"), messages.ERROR)
            return redirect(f"../../{client_id}/change/")

        client = task.client
        uploaded: Any = request.FILES["report_file"]

        rel_path = f"client_docs/{client.pk}/{client.name[:20]}_企业信用报告.pdf"
        abs_path = Path(settings.MEDIA_ROOT) / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        file_content = b""
        with abs_path.open("wb") as f:
            for chunk in uploaded.chunks():
                f.write(chunk)
                file_content += chunk

        doc, _ = ClientIdentityDoc.objects.get_or_create(
            client=client,
            doc_type=ClientIdentityDoc.BUSINESS_LICENSE,
        )
        doc.file_path = str(rel_path)
        doc.save(update_fields=["file_path"])

        # 使用端口标记任务成功
        gsxt_port.upload_report(
            task_id=task_id,
            file_content=file_content,
            file_name=rel_path,
        )

        self.message_user(
            request,
            _("报告已上传并保存为营业执照附件"),
            messages.SUCCESS,
        )
        return redirect(f"../../{client_id}/change/")

    def _check_oa_credential_view(self, request: HttpRequest) -> JsonResponse:
        """检查当前用户是否有金诚同达OA凭证。"""
        from django.db.models import Q

        lawyer_id = getattr(request.user, "id", None)
        if lawyer_id is None:
            return JsonResponse({"has_credential": False, "error": "无效用户"})

        from apps.organization.models import AccountCredential

        credential = AccountCredential.objects.filter(
            Q(account__icontains="jtn.com") | Q(url__icontains="jtn.com"),
            lawyer_id=lawyer_id,
        ).exists()

        return JsonResponse({"has_credential": credential})

    def get_changeform_initial_data(self, request: HttpRequest) -> dict[str, Any]:
        return {"client_type": "legal"}

    def get_inlines(self, request: HttpRequest, obj: Client | None = None) -> list[type[Any]]:
        inlines: list[type[Any]] = [ClientIdentityDocInline]
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
            has_business_license = any(info["doc_type"] == ClientIdentityDoc.BUSINESS_LICENSE for info in upload_info)
            if has_business_license:
                gsxt_port: GsxtReportPort = get_gsxt_report_port()
                task = gsxt_port.get_waiting_email_task(client_id=form.instance.id)
                if task:
                    gsxt_port.upload_report(
                        task_id=task.id,
                        file_content=b"",
                        file_name="manual_upload",
                    )

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

    def get_file_paths(self, queryset: QuerySet[Client]) -> list[str]:
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
