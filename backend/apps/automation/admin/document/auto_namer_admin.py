"""
自动命名工具Admin
独立的Admin模块
"""

from django import forms
from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.middleware.csrf import get_token
from django.conf import settings

from ...services.document.document_processing import process_uploaded_document
from ...services.ai.ollama_client import chat as ollama_chat
from ...services.ai.prompts import DEFAULT_FILENAME_PROMPT
from ...models import NamerTool


class AutoNamerToolForm(forms.Form):
    """自动命名工具表单"""
    upload = forms.FileField(
        required=True,
        help_text="支持PDF、DOCX和图片文件（JPG、PNG、BMP、TIFF等）"
    )
    prompt = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'rows': 8}),
        initial=DEFAULT_FILENAME_PROMPT,
        help_text="AI提示词，用于指导模型生成合适的文件名"
    )
    model = forms.CharField(
        required=True,
        initial="qwen3:0.6b",
        help_text="使用的AI模型名称"
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


@admin.register(NamerTool)
class AutoNamerToolAdmin(admin.ModelAdmin):
    """自动命名工具管理类"""
    
    change_list_template = None

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path("process/", self.admin_site.admin_view(self.process_view), name="%s_%s_process" % info),
            path("", self.admin_site.admin_view(self.redirect_to_process)),
        ]
        return custom + urls

    def redirect_to_process(self, request):
        info = self.model._meta.app_label, self.model._meta.model_name
        return HttpResponseRedirect(reverse("admin:%s_%s_process" % info))
    
    def process_view(self, request):
        """自动命名工具主视图"""
        if request.method == "POST":
            form = AutoNamerToolForm(request.POST, request.FILES)
            if form.is_valid():
                fp = form.cleaned_data["upload"]
                prompt = form.cleaned_data["prompt"]
                model = form.cleaned_data["model"]
                limit = form.cleaned_data.get("limit")
                preview_page = form.cleaned_data.get("preview_page")
                
                info = self.model._meta.app_label, self.model._meta.model_name
                return_url = reverse("admin:%s_%s_process" % info)
                
                try:
                    # 处理文档
                    extraction = process_uploaded_document(fp, limit=limit, preview_page=preview_page)
                except ValueError as e:
                    return HttpResponse(str(e))
                
                text = extraction.text or ""
                
                if extraction.kind not in {"pdf", "docx", "image"}:
                    return HttpResponse("不支持的文件类型，支持PDF、DOCX和图片文件（JPG、PNG等）")
                
                if not text.strip():
                    error_msg = "文档中没有提取到文字内容，无法生成命名。"
                    if extraction.kind == "image":
                        error_msg += "<br><em>提示：图片文件可能包含手写文字、复杂排版或图片质量较差，建议尝试更清晰的扫描件。</em>"
                    elif extraction.kind == "pdf":
                        error_msg += "<br><em>提示：PDF可能是扫描版或图片格式，系统已尝试OCR识别但未成功。</em>"
                    
                    html = f"""
                    <h1>自动命名工具（上传文档 + 提示词 → 模型生成）</h1>
                    <h2>❌ 处理失败</h2>
                    <div style='background:#fff3cd;border:1px solid #ffeaa7;border-radius:5px;padding:15px;margin:15px 0;'>
                        <p style='color:#856404;margin:0;'>{error_msg}</p>
                    </div>
                    <p><strong>文件信息：</strong></p>
                    <ul>
                        <li>文件类型: {extraction.kind.upper()}</li>
                        <li>文件路径: {extraction.file_path}</li>
                        <li>预览图: {'<a href="' + extraction.image_url + '" target="_blank">查看预览图</a>' if extraction.image_url else '无'}</li>
                    </ul>
                    <p><a href='{return_url}'>← 返回重新上传</a></p>
                    """
                    return HttpResponse(html)
                
                # 调用AI
                try:
                    messages = [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text}
                    ]
                    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
                    ollama_result = ollama_chat(model=model, messages=messages, base_url=base_url)
                    
                    # 处理不同的响应格式
                    response_text = "无返回内容"
                    if isinstance(ollama_result, dict):
                        if "message" in ollama_result and isinstance(ollama_result["message"], dict):
                            response_text = ollama_result["message"].get("content", "无返回内容")
                        elif "response" in ollama_result:
                            response_text = ollama_result["response"]
                        elif "content" in ollama_result:
                            response_text = ollama_result["content"]
                        else:
                            import json
                            response_text = json.dumps(ollama_result, ensure_ascii=False, indent=2)
                    
                    html = f"""
                    <h1>自动命名工具（上传文档 + 提示词 → 模型生成）</h1>
                    <div style='background:#e7f3ff;border:1px solid #b8daff;border-radius:5px;padding:15px;margin:15px 0;'>
                        <p style='margin:0;'><strong>📄 文件信息：</strong></p>
                        <ul style='margin:5px 0 0 20px;'>
                            <li>文件类型: {extraction.kind.upper()}</li>
                            <li>文本长度: {len(text)} 字符</li>
                        </ul>
                    </div>
                    
                    <h2>📝 提取的文字内容</h2>
                    <div style='background:#f8f9fa;padding:15px;border:1px solid #dee2e6;border-radius:5px;margin:10px 0;'>
                        <pre style='white-space:pre-wrap;max-height:400px;overflow:auto;margin:0;font-family:monospace;'>{text}</pre>
                    </div>
                    
                    <h2>🤖 Ollama 返回结果</h2>
                    <div style='background:#f0f8f0;padding:15px;border:1px solid #c3e6cb;border-radius:5px;margin:10px 0;'>
                        <pre style='white-space:pre-wrap;margin:0;font-family:monospace;'>{response_text}</pre>
                    </div>
                    
                    <div style='margin-top:20px;'>
                        <a href='{return_url}' style='display:inline-block;padding:8px 16px;background:#007bff;color:white;text-decoration:none;border-radius:4px;'>← 返回</a>
                    </div>
                    """
                    return HttpResponse(html)
                except Exception as e:
                    import traceback
                    error_detail = str(e)
                    error_traceback = traceback.format_exc()
                    html = f"""
                    <h1>自动命名工具（上传文档 + 提示词 → 模型生成）</h1>
                    <h2>处理失败</h2>
                    <div style='color: red; margin: 20px 0;'>
                        <h2>错误信息：</h2>
                        <pre style='white-space:pre-wrap;background:#f5f5f5;padding:10px;border:1px solid #ddd;'>{error_detail}</pre>
                    </div>
                    <details style='margin: 20px 0;'>
                        <summary style='cursor: pointer; color: #666;'>查看详细错误堆栈</summary>
                        <pre style='white-space:pre-wrap;background:#f5f5f5;padding:10px;border:1px solid #ddd;font-size:12px;'>{error_traceback}</pre>
                    </details>
                    <p><a href='{return_url}'>返回</a></p>
                    """
                    return HttpResponse(html)
        else:
            form = AutoNamerToolForm()
        
        csrf_token = get_token(request)
        html = f"""
        <h1>自动命名工具（上传文档 + 提示词 → 模型生成）</h1>
        <form method='post' enctype='multipart/form-data'>
            <input type='hidden' name='csrfmiddlewaretoken' value='{csrf_token}' />
            <p>
                <label>上传文件：</label><br/>
                <input type='file' name='upload' required/>
            </p>
            <p>
                <label>提示词：</label><br/>
                <textarea name='prompt' rows='8' required style='width:100%;'>{DEFAULT_FILENAME_PROMPT}</textarea>
            </p>
            <p>
                <label>模型名称：</label><br/>
                <input type='text' name='model' value='qwen3:0.6b' required style='width:100%;'/>
            </p>
            <p>
                <label>文字提取限制：</label><br/>
                <input type='number' name='limit' placeholder='留空使用默认值1500字' min='1' style='width:100%;'/>
            </p>
            <p>
                <label>PDF预览页码：</label><br/>
                <input type='number' name='preview_page' placeholder='留空使用默认值第1页' min='1' style='width:100%;'/>
            </p>
            <p><button type='submit' class='default'>提交处理</button></p>
        </form>
        """
        return HttpResponse(html)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False
