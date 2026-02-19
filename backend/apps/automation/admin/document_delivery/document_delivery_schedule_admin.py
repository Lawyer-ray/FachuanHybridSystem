"""
文书送达定时任务 Django Admin 界面

提供定时任务管理、手动触发查询等功能。
"""

from typing import ClassVar
import logging

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.automation.models import DocumentDeliverySchedule

logger = logging.getLogger("apps.automation")


def _get_document_delivery_schedule_service():
    """获取文书送达定时任务服务实例（工厂函数）"""
    from apps.automation.services.document_delivery.document_delivery_schedule_service import (
        DocumentDeliveryScheduleService,
    )

    return DocumentDeliveryScheduleService()


@admin.register(DocumentDeliverySchedule)
class DocumentDeliveryScheduleAdmin(admin.ModelAdmin):
    """文书送达定时任务管理"""

    # 列表显示字段
    list_display: ClassVar[list[str]] = [
        "id",
        "credential_display",
        "runs_per_day",
        "hour_interval",
        "cutoff_hours",
        "status_display",
        "last_run_display",
        "next_run_display",
        "created_at",
    ]

    # 列表筛选器
    list_filter: ClassVar[list[str]] = [
        "is_active",
        "runs_per_day",
        "hour_interval",
        "created_at",
        ("credential", admin.RelatedFieldListFilter),
    ]

    # 搜索字段
    search_fields: ClassVar[list[str]] = [
        "credential__account",
        "credential__site_name",
    ]

    # 排序
    ordering: ClassVar[list[str]] = ["-created_at"]
    # 分页
    list_per_page = 20

    # 只读字段
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "last_run_at",
        "next_run_at",
        "created_at",
        "updated_at",
        "manual_trigger_button",
    ]

    # 字段分组
    fieldsets = (
        (
            "基本信息",
            {
                "fields": (
                    "id",
                    "credential",
                    "is_active",
                )
            },
        ),
        (
            "调度配置",
            {
                "fields": (
                    "runs_per_day",
                    "hour_interval",
                    "cutoff_hours",
                ),
                "description": "配置定时任务的运行频率和时间范围",
            },
        ),
        (
            "运行状态",
            {
                "fields": (
                    "last_run_at",
                    "next_run_at",
                    "manual_trigger_button",
                )
            },
        ),
        (
            "时间戳",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    # 自定义操作
    actions: ClassVar[list[str]] = [
        "trigger_manual_query_action",
        "activate_schedules_action",
        "deactivate_schedules_action",
    ]

    def get_urls(self):
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:schedule_id>/trigger/",
                self.admin_site.admin_view(self.trigger_manual_query_view),
                name="automation_documentdeliveryschedule_trigger",
            ),
        ]
        return custom_urls + urls

    def credential_display(self, obj):
        """账号凭证显示"""
        if obj.credential:
            url = reverse("admin:organization_accountcredential_change", args=[obj.credential.id])
            return format_html(
                '<a href="{}" target="_blank">{} ({})</a>', url, obj.credential.account, obj.credential.site_name
            )
        return "-"

    credential_display.short_description = "账号凭证"

    def status_display(self, obj):
        """状态显示（带颜色）"""
        if obj.is_active:
            return format_html('<span style="color: green; font-weight: bold;">✓ 启用</span>')
        else:
            return format_html('<span style="color: red; font-weight: bold;">✗ 禁用</span>')

    status_display.short_description = "状态"

    def last_run_display(self, obj):
        """上次运行时间显示"""
        if obj.last_run_at:
            now = timezone.now()
            time_diff = now - obj.last_run_at

            if time_diff.days > 0:
                time_str = f"{time_diff.days} 天前"
                color = "orange" if time_diff.days > 1 else "blue"
            elif time_diff.seconds > 3600:
                hours = time_diff.seconds // 3600
                time_str = f"{hours} 小时前"
                color = "blue"
            elif time_diff.seconds > 60:
                minutes = time_diff.seconds // 60
                time_str = f"{minutes} 分钟前"
                color = "green"
            else:
                time_str = "刚刚"
                color = "green"

            return format_html(
                '<span style="color: {};">{}</span><br><small style="color: #666;">{}</small>',
                color,
                time_str,
                obj.last_run_at.strftime("%m-%d %H:%M"),
            )
        return format_html('<span style="color: gray;">从未运行</span>')

    last_run_display.short_description = "上次运行"

    def next_run_display(self, obj):
        """下次运行时间显示"""
        if not obj.is_active:
            return format_html('<span style="color: gray;">已禁用</span>')

        if obj.next_run_at:
            now = timezone.now()

            if obj.next_run_at <= now:
                return format_html(
                    '<span style="color: red; font-weight: bold;">⏰ 待执行</span><br>'
                    '<small style="color: #666;">{}</small>',
                    obj.next_run_at.strftime("%m-%d %H:%M"),
                )

            time_diff = obj.next_run_at - now

            if time_diff.days > 0:
                time_str = f"{time_diff.days} 天后"
                color = "blue"
            elif time_diff.seconds > 3600:
                hours = time_diff.seconds // 3600
                time_str = f"{hours} 小时后"
                color = "blue"
            elif time_diff.seconds > 60:
                minutes = time_diff.seconds // 60
                time_str = f"{minutes} 分钟后"
                color = "orange"
            else:
                time_str = "即将执行"
                color = "red"

            return format_html(
                '<span style="color: {};">{}</span><br><small style="color: #666;">{}</small>',
                color,
                time_str,
                obj.next_run_at.strftime("%m-%d %H:%M"),
            )
        return format_html('<span style="color: gray;">未设置</span>')

    next_run_display.short_description = "下次运行"

    def manual_trigger_button(self, obj):
        """手动触发按钮"""
        if obj.id and obj.credential:
            trigger_url = reverse("admin:automation_documentdeliveryschedule_trigger", args=[obj.id])
            return format_html(
                '<a href="{}" class="button" onclick="return confirm('
                "'确认要手动触发文书查询吗？这将立即执行一次查询任务。');"
                '">'
                "🚀 手动触发查询</a>",
                trigger_url,
            )
        return "-"

    manual_trigger_button.short_description = "操作"

    def trigger_manual_query_action(self, request, queryset):
        """手动触发查询操作（异步执行，不阻塞 Admin）"""
        import threading

        service = _get_document_delivery_schedule_service()
        triggered_count = 0
        error_count = 0

        for schedule in queryset:
            if not schedule.credential:
                error_count += 1
                continue

            # 在后台线程中执行，不阻塞 Admin
            def run_task(schedule_id):
                try:
                    service.execute_scheduled_task(schedule_id)
                    logger.info(f"后台文书查询任务完成: Schedule ID={schedule_id}")
                except Exception as e:
                    logger.error(f"后台文书查询任务失败: Schedule ID={schedule_id}, 错误: {e!s}")

            thread = threading.Thread(target=run_task, args=(schedule.id,), daemon=True)
            thread.start()
            triggered_count += 1
            logger.info(f"管理员触发后台文书查询: Schedule ID={schedule.id}, User={request.user}")

        if triggered_count > 0:
            messages.success(request, f"已在后台启动 {triggered_count} 个查询任务（不阻塞页面）")
        if error_count > 0:
            messages.error(request, f"触发失败 {error_count} 个任务（无账号凭证）")

    trigger_manual_query_action.short_description = "🚀 手动触发选中的查询任务"

    def activate_schedules_action(self, request, queryset):
        """启用定时任务操作"""
        updated = queryset.update(is_active=True)
        messages.success(request, f"成功启用 {updated} 个定时任务")
        logger.info(f"管理员批量启用定时任务: Count={updated}, User={request.user}")

    activate_schedules_action.short_description = "✓ 启用选中的定时任务"

    def deactivate_schedules_action(self, request, queryset):
        """禁用定时任务操作"""
        updated = queryset.update(is_active=False)
        messages.success(request, f"成功禁用 {updated} 个定时任务")
        logger.info(f"管理员批量禁用定时任务: Count={updated}, User={request.user}")

    deactivate_schedules_action.short_description = "✗ 禁用选中的定时任务"

    def trigger_manual_query_view(self, request, schedule_id):
        """手动触发查询视图（异步执行，不阻塞 Admin）"""
        import threading

        schedule = get_object_or_404(DocumentDeliverySchedule, id=schedule_id)

        if not schedule.credential:
            messages.error(request, "该定时任务没有关联的账号凭证")
        else:
            # 在后台线程中执行，不阻塞 Admin
            def run_task():
                try:
                    service = _get_document_delivery_schedule_service()
                    result = service.execute_scheduled_task(schedule_id)
                    logger.info(f"后台文书查询任务完成: Schedule ID={schedule_id}, Result={result}")
                except Exception as e:
                    logger.error(f"后台文书查询任务失败: Schedule ID={schedule_id}, 错误: {e!s}")

            thread = threading.Thread(target=run_task, daemon=True)
            thread.start()

            messages.success(request, "查询任务已在后台启动，请查看日志了解执行结果（不阻塞页面）")
            logger.info(f"管理员触发后台文书查询: Schedule ID={schedule_id}, User={request.user}")

        # 跳转回定时任务详情页
        return HttpResponseRedirect(reverse("admin:automation_documentdeliveryschedule_change", args=[schedule_id]))

    def get_queryset(self, request):
        """优化查询性能"""
        return super().get_queryset(request).select_related("credential")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """自定义外键字段"""
        if db_field.name == "credential":
            # 显示所有账号凭证，按网站名称和账号排序
            kwargs["queryset"] = db_field.related_model.objects.all().order_by("site_name", "account")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        """自定义表单"""
        form = super().get_form(request, obj, **kwargs)

        # 设置字段帮助文本
        if "runs_per_day" in form.base_fields:
            form.base_fields["runs_per_day"].help_text = "每天运行的次数，建议1-4次"

        if "hour_interval" in form.base_fields:
            form.base_fields["hour_interval"].help_text = "运行间隔小时数，应该是24除以runs_per_day的结果"

        if "cutoff_hours" in form.base_fields:
            form.base_fields["cutoff_hours"].help_text = "只处理最近N小时内的文书，建议24-72小时"

        return form

    def save_model(self, request, obj, form, change):
        """保存模型时的处理"""
        if not change:  # 新增时
            # 计算初始的下次运行时间
            service = _get_document_delivery_schedule_service()

            # 先保存对象
            super().save_model(request, obj, form, change)

            # 然后计算下次运行时间
            try:
                service.update_schedule(
                    obj.id,
                    runs_per_day=obj.runs_per_day,
                    hour_interval=obj.hour_interval,
                    cutoff_hours=obj.cutoff_hours,
                    is_active=obj.is_active,
                )
                messages.success(request, "定时任务创建成功！下次运行时间已自动计算")
                logger.info(f"管理员创建文书送达定时任务: Schedule ID={obj.id}, User={request.user}")

            except Exception as e:
                messages.warning(request, f"定时任务已创建，但下次运行时间计算失败: {e!s}")
                logger.error(f"管理员创建定时任务后计算下次运行时间失败: Schedule ID={obj.id}, 错误: {e!s}")
        else:
            # 更新时重新计算下次运行时间
            super().save_model(request, obj, form, change)

            try:
                service = _get_document_delivery_schedule_service()
                service.update_schedule(
                    obj.id,
                    runs_per_day=obj.runs_per_day,
                    hour_interval=obj.hour_interval,
                    cutoff_hours=obj.cutoff_hours,
                    is_active=obj.is_active,
                )
                logger.info(f"管理员更新文书送达定时任务: Schedule ID={obj.id}, User={request.user}")

            except Exception as e:
                messages.warning(request, f"定时任务已更新，但下次运行时间计算失败: {e!s}")
                logger.error(f"管理员更新定时任务后计算下次运行时间失败: Schedule ID={obj.id}, 错误: {e!s}")
