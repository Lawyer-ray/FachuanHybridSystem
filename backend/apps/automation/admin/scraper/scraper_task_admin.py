"""
爬虫任务 Admin
"""

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeData
from django.utils.translation import gettext_lazy as _

from apps.automation.models import ScraperTask

logger = logging.getLogger(__name__)


@admin.register(ScraperTask)
class ScraperTaskAdmin(admin.ModelAdmin[ScraperTask]):
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
    def status_colored(self, obj: Any) -> SafeData:
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
            obj.get_status_display(),
        )

    @admin.display(description="URL")
    def url_short(self, obj: Any) -> str:
        """缩短的 URL 显示"""
        url: str = str(obj.url)
        if len(url) > 50:
            return url[:50] + "..."
        return url

    @admin.display(description="重试")
    def retry_info(self, obj: Any) -> SafeData | str:
        """显示重试信息"""
        if obj.retry_count > 0:
            return format_html(
                '<span style="color: #ffa500;">{}/{}</span>',
                obj.retry_count,
                obj.max_retries,
            )
        return f"0/{obj.max_retries}"

    @admin.display(description="耗时")
    def duration(self, obj: Any) -> str:
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

    def _render_files_html(self, files: list[str]) -> SafeData:
        """渲染文件列表 HTML，返回安全的 format_html 结果"""
        from django.conf import settings

        def _file_item(f: str) -> SafeData:
            filename = f.split("/")[-1] if "/" in f else f
            try:
                file_path = Path(f)
                media_root = Path(settings.MEDIA_ROOT)
                relative_path = file_path.relative_to(media_root)
                file_url = settings.MEDIA_URL + str(relative_path)
                icon = self._file_icon(filename)
                return format_html(
                    '<li style="margin: 5px 0;">'
                    '<a href="{}" target="_blank" style="color: #0066cc; text-decoration: none;">'
                    "{} {}</a></li>",
                    file_url,
                    icon,
                    filename,
                )
            except Exception:
                icon = self._file_icon(filename)
                return format_html(
                    '<li style="margin: 5px 0;">{} {}</li>',
                    icon,
                    filename,
                )

        items = format_html_join("", "{}", ((_file_item(f),) for f in files))
        return format_html(
            '<div style="margin-top: 10px;"><strong>📁 下载的文件:</strong>'
            '<ul style="list-style: none; padding-left: 0;">{}</ul></div>',
            items,
        )

    def _render_screenshots_html(self, screenshots: list[str]) -> SafeData:
        """渲染截图列表 HTML，返回安全的 format_html 结果"""
        from django.conf import settings

        def _screenshot_item(ss: str) -> SafeData:
            if ss.startswith(str(settings.MEDIA_ROOT)):
                ss_url = ss.replace(str(settings.MEDIA_ROOT), settings.MEDIA_URL)
                return format_html(
                    '<br><img src="{}" style="max-width: 600px; border: 1px solid #ddd; margin-top: 10px;">',
                    ss_url,
                )
            return format_html("{}", "")

        return format_html_join("", "{}", ((_screenshot_item(ss),) for ss in screenshots))

    @admin.display(description="执行结果")
    def result_display(self, obj: Any) -> SafeData | str:
        """格式化显示结果"""
        if not obj.result:
            return "-"

        result_json = json.dumps(obj.result, indent=2, ensure_ascii=False)

        screenshot: str | None = obj.result.get("screenshot")
        screenshots: list[str] = obj.result.get("screenshots", [])
        files: list[str] = obj.result.get("files", [])

        pre_block = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px;'
            ' max-height: 300px; overflow: auto;">{}</pre>',
            result_json,
        )

        files_block = self._render_files_html(files) if files else format_html("{}", "")

        if screenshot:
            from django.conf import settings

            if screenshot.startswith(str(settings.MEDIA_ROOT)):
                screenshot_url = screenshot.replace(str(settings.MEDIA_ROOT), settings.MEDIA_URL)
                single_screenshot_block = format_html(
                    '<br><img src="{}" style="max-width: 600px; border: 1px solid #ddd;">',
                    screenshot_url,
                )
            else:
                single_screenshot_block = format_html("{}", "")
        else:
            single_screenshot_block = format_html("{}", "")

        screenshots_block = self._render_screenshots_html(screenshots) if screenshots else format_html("{}", "")

        return format_html(
            "{}{}{}{}",
            pre_block,
            files_block,
            single_screenshot_block,
            screenshots_block,
        )

    @admin.action(description=_("立即执行选中的任务"))
    def execute_tasks(self, request: Any, queryset: Any) -> None:
        """批量执行任务"""
        from django_q.tasks import async_task

        count = 0
        for task in queryset:
            if task.status in ["pending", "failed"]:
                async_task("apps.automation.tasks.execute_scraper_task", task.id)
                count += 1

        logger.info("已提交 %d 个任务到后台队列", count)
        self.message_user(request, _(f"已提交 {count} 个任务到后台队列"))

    @admin.action(description=_("重置失败任务状态"))
    def reset_failed_tasks(self, request: Any, queryset: Any) -> None:
        """重置失败任务，允许重新执行"""
        count = queryset.filter(status="failed").update(status="pending", retry_count=0, error_message=None)
        logger.info("已重置 %d 个失败任务", count)
        self.message_user(request, _(f"已重置 {count} 个失败任务"))
