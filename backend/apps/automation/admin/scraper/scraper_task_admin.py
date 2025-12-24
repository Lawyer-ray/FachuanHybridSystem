"""
爬虫任务 Admin
"""
from django.contrib import admin
from django.utils.html import format_html
from ...models import ScraperTask


@admin.register(ScraperTask)
class ScraperTaskAdmin(admin.ModelAdmin):
    """爬虫任务管理"""
    list_display = (
        "id",
        "task_type",
        "priority",
        "status_colored",
        "retry_info",
        "url_short",
        "case",
        "created_at",
        "duration",
    )
    list_filter = ("task_type", "status", "priority", "created_at")
    search_fields = ("url", "error_message")
    readonly_fields = (
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "result_display",
        "error_message",
        "retry_count",
    )
    fieldsets = (
        ("基本信息", {
            "fields": ("task_type", "status", "priority", "url", "case")
        }),
        ("重试配置", {
            "fields": ("retry_count", "max_retries", "scheduled_at")
        }),
        ("配置", {
            "fields": ("config",),
            "classes": ("collapse",)
        }),
        ("执行结果", {
            "fields": ("result_display", "error_message")
        }),
        ("时间信息", {
            "fields": ("created_at", "started_at", "finished_at", "updated_at")
        }),
    )
    
    @admin.display(description="状态")
    def status_colored(self, obj):
        """带颜色的状态显示"""
        colors = {
            "pending": "#ffa500",
            "running": "#007bff",
            "success": "#28a745",
            "failed": "#dc3545",
        }
        color = colors.get(obj.status, "#666")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    
    @admin.display(description="URL")
    def url_short(self, obj):
        """缩短的 URL 显示"""
        if len(obj.url) > 50:
            return obj.url[:50] + "..."
        return obj.url
    
    @admin.display(description="重试")
    def retry_info(self, obj):
        """显示重试信息"""
        if obj.retry_count > 0:
            return format_html(
                '<span style="color: #ffa500;">{}/{}</span>',
                obj.retry_count,
                obj.max_retries
            )
        return f"0/{obj.max_retries}"
    
    @admin.display(description="耗时")
    def duration(self, obj):
        """计算任务耗时"""
        if obj.started_at and obj.finished_at:
            delta = obj.finished_at - obj.started_at
            seconds = delta.total_seconds()
            if seconds < 60:
                return f"{seconds:.1f}秒"
            else:
                minutes = seconds / 60
                return f"{minutes:.1f}分钟"
        return "-"
    
    @admin.display(description="执行结果")
    def result_display(self, obj):
        """格式化显示结果"""
        if not obj.result:
            return "-"
        
        import json
        from django.utils.html import escape
        from django.utils.safestring import mark_safe
        
        result_json = json.dumps(obj.result, indent=2, ensure_ascii=False)
        # 转义 HTML 特殊字符，避免 format_html 的占位符问题
        escaped_json = escape(result_json)
        
        # 如果结果中有截图，显示图片
        screenshot = obj.result.get("screenshot")
        screenshots = obj.result.get("screenshots", [])
        files = obj.result.get("files", [])
        
        html_parts = [f'<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; max-height: 300px; overflow: auto;">{escaped_json}</pre>']
        
        # 显示下载的文件列表（带下载链接）
        if files:
            from django.conf import settings
            from pathlib import Path
            
            html_parts.append('<div style="margin-top: 10px;"><strong>📁 下载的文件:</strong><ul style="list-style: none; padding-left: 0;">')
            for f in files:
                filename = f.split('/')[-1] if '/' in f else f
                
                # 尝试生成下载链接
                try:
                    file_path = Path(f)
                    media_root = Path(settings.MEDIA_ROOT)
                    relative_path = file_path.relative_to(media_root)
                    file_url = settings.MEDIA_URL + str(relative_path)
                    
                    # 根据文件类型显示不同图标
                    if filename.endswith('.pdf'):
                        icon = '📄'
                    elif filename.endswith('.zip'):
                        icon = '📦'
                    elif filename.endswith(('.doc', '.docx')):
                        icon = '📝'
                    else:
                        icon = '📎'
                    
                    html_parts.append(
                        f'<li style="margin: 5px 0;">'
                        f'<a href="{escape(file_url)}" target="_blank" style="color: #0066cc; text-decoration: none;">'
                        f'{icon} {escape(filename)}'
                        f'</a>'
                        f'</li>'
                    )
                except (ValueError, Exception):
                    # 如果无法生成链接，只显示文件名
                    html_parts.append(f'<li style="margin: 5px 0;">📎 {escape(filename)}</li>')
            
            html_parts.append('</ul></div>')
        
        # 显示单个截图
        if screenshot:
            from django.conf import settings
            if screenshot.startswith(str(settings.MEDIA_ROOT)):
                screenshot_url = screenshot.replace(str(settings.MEDIA_ROOT), settings.MEDIA_URL)
                html_parts.append(
                    f'<br><img src="{escape(screenshot_url)}" style="max-width: 600px; border: 1px solid #ddd;">'
                )
        
        # 显示多个截图
        if screenshots:
            from django.conf import settings
            for ss in screenshots:
                if ss.startswith(str(settings.MEDIA_ROOT)):
                    ss_url = ss.replace(str(settings.MEDIA_ROOT), settings.MEDIA_URL)
                    html_parts.append(
                        f'<br><img src="{escape(ss_url)}" style="max-width: 600px; border: 1px solid #ddd; margin-top: 10px;">'
                    )
        
        return mark_safe(''.join(html_parts))
    
    # Admin 操作
    actions = ["execute_tasks", "reset_failed_tasks"]
    
    @admin.action(description="立即执行选中的任务")
    def execute_tasks(self, request, queryset):
        """批量执行任务"""
        from django_q.tasks import async_task
        
        count = 0
        for task in queryset:
            if task.status in ["pending", "failed"]:
                async_task("apps.automation.tasks.execute_scraper_task", task.id)
                count += 1
        
        self.message_user(request, f"已提交 {count} 个任务到后台队列")
    
    @admin.action(description="重置失败任务状态")
    def reset_failed_tasks(self, request, queryset):
        """重置失败任务，允许重新执行"""
        count = queryset.filter(status="failed").update(
            status="pending",
            retry_count=0,
            error_message=None
        )
        self.message_user(request, f"已重置 {count} 个失败任务")
