"""
爬虫任务 Admin
"""

from typing import Any, ClassVar
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.automation.models import ScraperTask


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
        (_("基本信息"), {"fields": ("task_type", "status", "priority", "url", "case")}),
        (_("重试配置"), {"fields": ("retry_count", "max_retries", "scheduled_at")}),
        (_("配置"), {"fields": ("config",), "classes": ("collapse",)}),
        (_("执行结果"), {"fields": ("result_display", "error_message")}),
        (_("时间信息"), {"fields": ("created_at", "started_at", "finished_at", "updated_at")}),
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
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

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
            return format_html('<span style="color: #ffa500;">{}/{}</span>', obj.retry_count, obj.max_retries)
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

    def _file_icon(self, filename: str) -> str:
        """根据文件扩展名返回图标"""
        if filename.endswith(".pdf"):
            return "📄"
        if filename.endswith(".zip"):
            return "📦"
        if filename.endswith((".doc", ".docx")):
            return "📝"
        return "📎"

    def _render_files_html(self, files: list[str]) -> list[str]:
        """渲染文件列表 HTML"""
        from pathlib import Path

        from django.conf import settings
        from django.utils.html import escape

        parts = [
            '<div style="margin-top: 10px;"><strong>📁 下载的文件:</strong>'
            '<ul style="list-style: none; padding-left: 0;">',
        ]
        for f in files:
            filename = f.split("/")[-1] if "/" in f else f
            try:
                file_path = Path(f)
                media_root = Path(settings.MEDIA_ROOT)
                relative_path = file_path.relative_to(media_root)
                file_url = settings.MEDIA_URL + str(relative_path)
                icon = self._file_icon(filename)
                parts.append(
                    f'<li style="margin: 5px 0;">'
                    f'<a href="{escape(file_url)}" target="_blank" style="color: #0066cc; text-decoration: none;">'
                    f"{icon} {escape(filename)}</a></li>"
                )
            except (ValueError, Exception):
                parts.append(f'<li style="margin: 5px 0;">📎 {escape(filename)}</li>')
        parts.append("</ul></div>")
        return parts

    def _render_screenshots_html(self, screenshots: list[str]) -> list[str]:
        """渲染截图列表 HTML"""
        from django.conf import settings
        from django.utils.html import escape

        parts = []
        for ss in screenshots:
            if ss.startswith(str(settings.MEDIA_ROOT)):
                ss_url = ss.replace(str(settings.MEDIA_ROOT), settings.MEDIA_URL)
                parts.append(
                    f'<br><img src="{escape(ss_url)}" '
                    f'style="max-width: 600px; border: 1px solid #ddd; margin-top: 10px;">'
                )
        return parts

    @admin.display(description="执行结果")
    def result_display(self, obj: Any) -> Any:
        """格式化显示结果"""
        if not obj.result:
            return "-"

        import json

        from django.utils.html import escape
        from django.utils.safestring import mark_safe

        result_json = json.dumps(obj.result, indent=2, ensure_ascii=False)
        escaped_json = escape(result_json)

        screenshot = obj.result.get("screenshot")
        screenshots = obj.result.get("screenshots", [])
        files = obj.result.get("files", [])

        html_parts = [
            f'<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px;'
            f' max-height: 300px; overflow: auto;">{escaped_json}</pre>'
        ]

        if files:
            html_parts.extend(self._render_files_html(files))

        if screenshot:
            from django.conf import settings
            if screenshot.startswith(str(settings.MEDIA_ROOT)):
                screenshot_url = screenshot.replace(str(settings.MEDIA_ROOT), settings.MEDIA_URL)
                html_parts.append(
                    f'<br><img src="{escape(screenshot_url)}" style="max-width: 600px; border: 1px solid #ddd;">'
                )

        if screenshots:
            html_parts.extend(self._render_screenshots_html(screenshots))

        return mark_safe("".join(html_parts))

    @admin.action(description=_("立即执行选中的任务"))
    def execute_tasks(self, request, queryset):
        """批量执行任务"""
        from django_q.tasks import async_task

        count = 0
        for task in queryset:
            if task.status in ["pending", "failed"]:
                async_task("apps.automation.tasks.execute_scraper_task", task.id)
                count += 1

        self.message_user(request, _(f"已提交 {count} 个任务到后台队列"))

    @admin.action(description=_("重置失败任务状态"))
    def reset_failed_tasks(self, request, queryset):
        """重置失败任务，允许重新执行"""
        count = queryset.filter(status="failed").update(status="pending", retry_count=0, error_message=None)
        self.message_user(request, _(f"已重置 {count} 个失败任务"))
