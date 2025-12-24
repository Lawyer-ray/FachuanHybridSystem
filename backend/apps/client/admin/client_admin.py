from django.contrib import admin
from django import forms
import os
from django.utils.html import format_html
from ..models import Client, ClientIdentityDoc


def _get_admin_service():
    """工厂函数：创建 ClientAdminService 实例"""
    from ..services import ClientAdminService
    return ClientAdminService()


class ClientIdentityDocInlineForm(forms.ModelForm):
    upload = forms.FileField(required=False, label="上传文件")

    class Meta:
        model = ClientIdentityDoc
        fields = ["doc_type", "upload"]


class ClientIdentityDocInline(admin.TabularInline):
    model = ClientIdentityDoc
    form = ClientIdentityDocInlineForm
    extra = 1
    fields = ("doc_type", "file_link", "upload")
    readonly_fields = ("file_link",)

    def file_link(self, obj):
        url = obj.media_url()
        if url:
            return format_html('<a href="{}" target="_blank">{}</a>', url, os.path.basename(obj.file_path))
        return ""


class ClientAdminForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = "__all__"

    class Media:
        css = {
            'all': ('client/admin.css',)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ct = None
        if self.instance and getattr(self.instance, "client_type", None):
            ct = self.instance.client_type
        elif "client_type" in self.data:
            ct = self.data.get("client_type")
        elif self.initial.get("client_type"):
            ct = self.initial.get("client_type")
        self.fields["id_number"].label = "身份证号码" if ct == "natural" else "统一社会信用代码"

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "client_type", "is_our_client", "phone", "legal_representative")
    search_fields = ("name", "phone", "id_number")
    list_filter = ("client_type", "is_our_client")
    form = ClientAdminForm
    
    def get_changeform_initial_data(self, request):
        return {"client_type": "legal"}
    
    inlines = []
    
    def get_inlines(self, request, obj=None):
        return [ClientIdentityDocInline]

    def save_formset(self, request, form, formset, change):
        # 收集需要处理的上传文件信息（在 save 之前）
        upload_info = []
        for f in formset.forms:
            if not f.cleaned_data:
                continue
            if f.cleaned_data.get('DELETE'):
                continue
            uploaded_file = f.cleaned_data.get('upload')
            if uploaded_file:
                upload_info.append({
                    'form': f,
                    'uploaded_file': uploaded_file,
                    'doc_type': f.cleaned_data.get('doc_type'),
                })
        
        # 调用父类 save，让 Django 处理保存和设置 new_objects 等属性
        instances = formset.save()
        
        # 处理文件上传和重命名
        if upload_info:
            admin_service = _get_admin_service()
            client = form.instance
            
            for info in upload_info:
                instance = info['form'].instance
                if instance.pk:
                    try:
                        admin_service.save_and_rename_file(
                            client_id=client.id,
                            client_name=client.name,
                            doc_id=instance.pk,
                            doc_type=info['doc_type'],
                            uploaded_file=info['uploaded_file']
                        )
                    except Exception as e:
                        import logging
                        logging.getLogger("apps.client").error(f"文件处理失败: {e}")
