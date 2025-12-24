from django.contrib import admin
from django.utils.html import format_html
from django import forms
import os
from ..models import PropertyClue, PropertyClueAttachment


class PropertyClueAttachmentInlineForm(forms.ModelForm):
    """财产线索附件内联表单"""
    file_upload = forms.FileField(required=False, label="上传文件")
    
    class Meta:
        model = PropertyClueAttachment
        fields = ("file_name", "file_path")
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # 处理文件上传
        if self.cleaned_data.get("file_upload"):
            uploaded_file = self.cleaned_data["file_upload"]
            
            # 确保目录存在
            from django.conf import settings
            base_dir = os.path.join(
                settings.MEDIA_ROOT, 
                "property_clue_attachments", 
                str(instance.property_clue.id)
            )
            os.makedirs(base_dir, exist_ok=True)
            
            # 保存文件
            file_path = os.path.join(base_dir, uploaded_file.name)
            with open(file_path, "wb+") as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            
            # 更新实例
            instance.file_path = os.path.abspath(file_path)
            instance.file_name = uploaded_file.name
        
        if commit:
            instance.save()
        
        return instance


class PropertyClueAttachmentInline(admin.TabularInline):
    """财产线索附件内联编辑"""
    model = PropertyClueAttachment
    form = PropertyClueAttachmentInlineForm
    extra = 1
    fields = ("file_upload", "file_name", "file_link", "uploaded_at")
    readonly_fields = ("file_link", "uploaded_at")

    def file_link(self, obj):
        """显示文件链接"""
        if obj.id:
            url = obj.media_url()
            if url:
                return format_html('<a href="{}" target="_blank">{}</a>', url, obj.file_name)
        return obj.file_name if obj.file_name else ""
    file_link.short_description = "文件"


@admin.register(PropertyClue)
class PropertyClueAdmin(admin.ModelAdmin):
    """财产线索管理"""
    list_display = ("id", "client", "clue_type_display", "content_preview", "attachment_count", "created_at", "updated_at")
    list_filter = ("clue_type", "created_at")
    search_fields = ("client__name", "content")
    readonly_fields = ("created_at", "updated_at")
    inlines = [PropertyClueAttachmentInline]
    
    fieldsets = (
        ("基本信息", {
            "fields": ("client", "clue_type", "content")
        }),
        ("时间信息", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def clue_type_display(self, obj):
        """显示线索类型标签"""
        return obj.get_clue_type_display()
    clue_type_display.short_description = "线索类型"

    def content_preview(self, obj):
        """显示内容摘要"""
        if obj.content:
            preview = obj.content[:50]
            if len(obj.content) > 50:
                preview += "..."
            return preview
        return ""
    content_preview.short_description = "内容摘要"

    def attachment_count(self, obj):
        """显示附件数量"""
        count = obj.attachments.count()
        if count > 0:
            return format_html('<span style="color: green;">{} 个附件</span>', count)
        return "无附件"
    attachment_count.short_description = "附件"
