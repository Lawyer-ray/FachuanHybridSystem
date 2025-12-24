"""
文档处理工具Admin
独立的Admin模块
"""

from django import forms
from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.middleware.csrf import get_token

from ...services.document.document_processing import process_uploaded_document
from ...models import AutomationTool


class DocumentProcessorForm(forms.Form):
    """文档处理工具表单"""
    upload = forms.FileField(
        required=True,
        help_text="支持PDF、DOCX和图片文件（JPG、PNG、BMP、TIFF等）"
    )
    limit = forms.IntegerField(
        required=False,
        help_text="文字提取限制（留空使用默认值1500字）"
    )
    preview_page = forms.IntegerField(
        required=False,
        min_value=1,
        help_text="PDF预览页码（留空使用默认值第1页）"
    )


# @admin.register(AutomationTool)  # 隐藏文档处理模块，不在Django后台显示
class DocumentProcessorAdmin(admin.ModelAdmin):
    """文档处理工具管理类"""
    
    change_list_template = None

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path("process-document/", self.admin_site.admin_view(self.process_view), name="%s_%s_process_document" % info),
            path("", self.admin_site.admin_view(self.redirect_to_process)),
        ]
        return custom + urls

    def redirect_to_process(self, request):
        info = self.model._meta.app_label, self.model._meta.model_name
        return HttpResponseRedirect(reverse("admin:%s_%s_process_document" % info))

    def process_view(self, request):
        """文档处理主视图"""
        if request.method == "POST":
            form = DocumentProcessorForm(request.POST, request.FILES)
            if form.is_valid():
                fp = form.cleaned_data["upload"]
                limit = form.cleaned_data.get("limit")
                preview_page = form.cleaned_data.get("preview_page")
                
                try:
                    extraction = process_uploaded_document(fp, limit=limit, preview_page=preview_page)
                except ValueError as e:
                    return HttpResponse(str(e))
                
                # 构建响应信息
                file_info = f"<p><strong>文件类型:</strong> {extraction.kind.upper()}</p>"
                file_info += f"<p><strong>文件路径:</strong> {extraction.file_path}</p>"
                
                if extraction.text:
                    html = f"""
                    <h1>文档处理（文件预览/文本抽取）</h1>
                    {file_info}
                    <h2>📝 提取的文本内容</h2>
                    <div style='background:#f8f9fa;padding:15px;border:1px solid #dee2e6;border-radius:5px;'>
                        <pre style='white-space:pre-wrap;margin:0;font-family:monospace;'>{extraction.text}</pre>
                    </div>
                    <p><strong>文本长度:</strong> {len(extraction.text)} 字符</p>
                    <p><a href='javascript:history.back()'>← 返回</a></p>
                    """
                    return HttpResponse(html)
                elif extraction.image_url:
                    html = f"""
                    <h1>文档处理（文件预览/文本抽取）</h1>
                    {file_info}
                    <h2>🖼️ 预览图（无法提取文本）</h2>
                    <p><em>该文件无法直接提取文字内容，已生成预览图供查看：</em></p>
                    <div style='text-align:center;background:#f8f9fa;padding:15px;border:1px solid #dee2e6;border-radius:5px;'>
                        <img src='{extraction.image_url}' style='max-width:100%;max-height:600px;border:1px solid #ddd;'/>
                    </div>
                    <p><a href='javascript:history.back()'>← 返回</a></p>
                    """
                    return HttpResponse(html)
                else:
                    html = f"""
                    <h1>文档处理（文件预览/文本抽取）</h1>
                    {file_info}
                    <h2>❌ 处理结果</h2>
                    <p style='color:orange;'>未提取到可展示的内容。可能的原因：</p>
                    <ul>
                        <li>文件为空或损坏</li>
                        <li>图片内容无法识别（如：纯图片、手写文字等）</li>
                        <li>PDF文件加密或权限限制</li>
                    </ul>
                    <p><a href='javascript:history.back()'>← 返回重新上传</a></p>
                    """
                    return HttpResponse(html)
        else:
            form = DocumentProcessorForm()
        
        csrf_token = get_token(request)
        html = f"""
        <h1>文档处理（文件预览/文本抽取）</h1>
        <form method='post' enctype='multipart/form-data'>
            <input type='hidden' name='csrfmiddlewaretoken' value='{csrf_token}' />
            <p><label>上传文件：</label><br/><input type='file' name='upload' required/></p>
            <p><label>文字提取限制：</label><br/><input type='number' name='limit' placeholder='留空使用默认值1500字' min='1'/></p>
            <p><label>PDF预览页码：</label><br/><input type='number' name='preview_page' placeholder='留空使用默认值第1页' min='1'/></p>
            <p><button type='submit' class='default'>提交处理</button></p>
        </form>
        """
        return HttpResponse(html)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_view_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
