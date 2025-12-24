from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from django import forms
import os
from ..models import ClientIdentityDoc


def _get_identity_doc_service():
    """工厂函数：获取当事人证件服务"""
    from ..services.client_identity_doc_service import ClientIdentityDocService
    return ClientIdentityDocService()


class ClientIdentityDocForm(forms.ModelForm):
    """当事人证件表单"""
    file_upload = forms.FileField(
        label="上传文件",
        required=False,
        help_text="上传后将自动重命名为：当事人名称_证件类型.扩展名"
    )
    
    class Meta:
        model = ClientIdentityDoc
        fields = ['client', 'doc_type', 'file_path']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['file_upload'].help_text = f"当前文件：{os.path.basename(self.instance.file_path or '')}"
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # 处理文件上传
        if self.cleaned_data.get('file_upload'):
            uploaded_file = self.cleaned_data['file_upload']
            
            # 保存文件到临时位置
            from django.conf import settings
            import tempfile
            import shutil
            
            # 创建目录
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'client_identity_docs')
            os.makedirs(upload_dir, exist_ok=True)
            
            # 生成文件名
            _, ext = os.path.splitext(uploaded_file.name)
            client_name = instance.client.name if instance.client else "未知"
            doc_type_display = instance.get_doc_type_display()
            
            # 清理文件名
            service = _get_identity_doc_service()
            clean_client_name = service._sanitize_filename(client_name)
            clean_doc_type = service._sanitize_filename(doc_type_display)
            
            new_filename = f"{clean_client_name}_{clean_doc_type}{ext}"
            file_path = os.path.join(upload_dir, new_filename)
            
            # 处理重名文件
            counter = 1
            original_path = file_path
            while os.path.exists(file_path):
                name_part = f"{clean_client_name}_{clean_doc_type}_{counter}"
                file_path = os.path.join(upload_dir, f"{name_part}{ext}")
                counter += 1
            
            # 保存文件
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            instance.file_path = file_path
        
        if commit:
            instance.save()
        return instance


@admin.register(ClientIdentityDoc)
class ClientIdentityDocAdmin(admin.ModelAdmin):
    form = ClientIdentityDocForm
    list_display = ("id", "client", "doc_type", "uploaded_at", "file_link")
    search_fields = ("client__name", "file_path")
    list_filter = ("doc_type",)
    actions = ["rename_files"]
    fields = ("client", "doc_type", "file_upload", "file_path")

    def file_link(self, obj):
        url = obj.media_url()
        if url:
            return format_html('<a href="{}" target="_blank">{}</a>', url, os.path.basename(obj.file_path))
        return obj.file_path
    file_link.short_description = "文件"
    
    def save_model(self, request, obj, form, change):
        """保存时自动重命名文件"""
        super().save_model(request, obj, form, change)
        
        service = _get_identity_doc_service()
        try:
            service.rename_uploaded_file(obj)
            if change:
                messages.success(request, f"文件已重命名为标准格式")
        except Exception as e:
            messages.warning(request, f"文件重命名失败: {str(e)}")
    
    def rename_files(self, request, queryset):
        """批量重命名文件"""
        service = _get_identity_doc_service()
        success_count = 0
        error_count = 0
        
        for obj in queryset:
            try:
                service.rename_uploaded_file(obj)
                success_count += 1
            except Exception:
                error_count += 1
        
        if success_count > 0:
            messages.success(request, f"成功重命名 {success_count} 个文件")
        if error_count > 0:
            messages.error(request, f"{error_count} 个文件重命名失败")
    
    rename_files.short_description = "重命名选中的文件"
