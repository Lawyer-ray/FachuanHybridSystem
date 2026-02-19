"""
法院短信处理 Django Admin 界面

提供短信记录管理、状态查看、手动处理等功能。
"""

from typing import Any, ClassVar
import logging

from django.contrib import admin, messages
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType

logger = logging.getLogger("apps.automation")


def _get_court_sms_service():
    """获取法院短信服务实例（工厂函数）"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_court_sms_service()


def _get_case_service():
    """获取案件服务实例（工厂函数）"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_case_service()


@admin.register(CourtSMS)
class CourtSMSAdmin(admin.ModelAdmin):
    """法院短信管理"""

    # 列表显示字段
    list_display: ClassVar[list[str]] = [
        "id",
        "status_display",
        "sms_type_display",
        "case_display",
        "content_preview",
        "received_at",
        "has_download_links",
        "case_numbers_display",
        "party_names_display",
        "feishu_status",
        "retry_count",
    ]

    # 列表筛选器
    list_filter: ClassVar[list[str]] = [
        "status",
        "sms_type",
        "received_at",
        ("case", admin.RelatedFieldListFilter),
        ("scraper_task", admin.RelatedFieldListFilter),
    ]

    # 搜索字段
    search_fields: ClassVar[list[str]] = [
        "content",
        "case__name",
    ]

    # 排序
    ordering: ClassVar[list[str]] = ["-received_at"]
    # 分页
    list_per_page = 20

    # 只读字段
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "created_at",
        "updated_at",
        "download_links_display",
        "case_numbers_display",
        "party_names_display",
        "scraper_task_link",
        "case_log_link",
        "documents_display",
        "feishu_details",
        "retry_button",
    ]

    # 字段分组
    fieldsets = (
        (
            "基本信息",
            {
                "fields": (
                    "id",
                    "content",
                    "received_at",
                    "status",
                    "sms_type",
                )
            },
        ),
        (
            "解析结果",
            {
                "fields": (
                    "download_links_display",
                    "case_numbers_display",
                    "party_names_display",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "关联信息",
            {
                "fields": (
                    "case",
                    "scraper_task_link",
                    "case_log_link",
                    "documents_display",
                )
            },
        ),
        (
            "处理状态",
            {
                "fields": (
                    "error_message",
                    "retry_count",
                    "retry_button",
                )
            },
        ),
        (
            "飞书通知",
            {
                "fields": ("feishu_details",),
                "classes": ("collapse",),
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
    actions: ClassVar[list[str]] = ["retry_processing_action"]

    def get_urls(self):
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls = [
            path("submit/", self.admin_site.admin_view(self.submit_sms_view), name="automation_courtsms_submit"),
            path("add2/", self.admin_site.admin_view(self.add2_view), name="automation_courtsms_add2"),
            path("add3/", self.admin_site.admin_view(self.add3_view), name="automation_courtsms_add3"),
            path("add4/", self.admin_site.admin_view(self.add4_view), name="automation_courtsms_add4"),
            path("add5/", self.admin_site.admin_view(self.add5_view), name="automation_courtsms_add5"),
            path("add6/", self.admin_site.admin_view(self.add6_view), name="automation_courtsms_add6"),
            path("add7/", self.admin_site.admin_view(self.add7_view), name="automation_courtsms_add7"),
            path("add8/", self.admin_site.admin_view(self.add8_view), name="automation_courtsms_add8"),
            path("add9/", self.admin_site.admin_view(self.add9_view), name="automation_courtsms_add9"),
            path("add10/", self.admin_site.admin_view(self.add10_view), name="automation_courtsms_add10"),
            path("add11/", self.admin_site.admin_view(self.add11_view), name="automation_courtsms_add11"),
            path("add12/", self.admin_site.admin_view(self.add12_view), name="automation_courtsms_add12"),
            path("add13/", self.admin_site.admin_view(self.add13_view), name="automation_courtsms_add13"),
            path("add14/", self.admin_site.admin_view(self.add14_view), name="automation_courtsms_add14"),
            path("add15/", self.admin_site.admin_view(self.add15_view), name="automation_courtsms_add15"),
            path("add16/", self.admin_site.admin_view(self.add16_view), name="automation_courtsms_add16"),
            path("add17/", self.admin_site.admin_view(self.add17_view), name="automation_courtsms_add17"),
            path("add18/", self.admin_site.admin_view(self.add18_view), name="automation_courtsms_add18"),
            path("add19/", self.admin_site.admin_view(self.add19_view), name="automation_courtsms_add19"),
            path("add20/", self.admin_site.admin_view(self.add20_view), name="automation_courtsms_add20"),
            path("add21/", self.admin_site.admin_view(self.add21_view), name="automation_courtsms_add21"),
            path("add22/", self.admin_site.admin_view(self.add22_view), name="automation_courtsms_add22"),
            path("add23/", self.admin_site.admin_view(self.add23_view), name="automation_courtsms_add23"),
            path("add24/", self.admin_site.admin_view(self.add24_view), name="automation_courtsms_add24"),
            path("add25/", self.admin_site.admin_view(self.add25_view), name="automation_courtsms_add25"),
            path("add26/", self.admin_site.admin_view(self.add26_view), name="automation_courtsms_add26"),
            path("add27/", self.admin_site.admin_view(self.add27_view), name="automation_courtsms_add27"),
            path("add28/", self.admin_site.admin_view(self.add28_view), name="automation_courtsms_add28"),
            path("add29/", self.admin_site.admin_view(self.add29_view), name="automation_courtsms_add29"),
            path("add30/", self.admin_site.admin_view(self.add30_view), name="automation_courtsms_add30"),
            path("add31/", self.admin_site.admin_view(self.add31_view), name="automation_courtsms_add31"),
            path("add32/", self.admin_site.admin_view(self.add32_view), name="automation_courtsms_add32"),
            path("add33/", self.admin_site.admin_view(self.add33_view), name="automation_courtsms_add33"),
            path("add34/", self.admin_site.admin_view(self.add34_view), name="automation_courtsms_add34"),
            path("add35/", self.admin_site.admin_view(self.add35_view), name="automation_courtsms_add35"),
            path("add36/", self.admin_site.admin_view(self.add36_view), name="automation_courtsms_add36"),
            path("add37/", self.admin_site.admin_view(self.add37_view), name="automation_courtsms_add37"),
            path("add38/", self.admin_site.admin_view(self.add38_view), name="automation_courtsms_add38"),
            path("add39/", self.admin_site.admin_view(self.add39_view), name="automation_courtsms_add39"),
            path("add40/", self.admin_site.admin_view(self.add40_view), name="automation_courtsms_add40"),
            path("add41/", self.admin_site.admin_view(self.add41_view), name="automation_courtsms_add41"),
            path(
                "<int:sms_id>/assign-case/",
                self.admin_site.admin_view(self.assign_case_view),
                name="automation_courtsms_assign_case",
            ),
            path(
                "<int:sms_id>/search-cases/",
                self.admin_site.admin_view(self.search_cases_ajax),
                name="automation_courtsms_search_cases",
            ),
            path(
                "<int:sms_id>/retry/",
                self.admin_site.admin_view(self.retry_single_sms_view),
                name="automation_courtsms_retry",
            ),
        ]
        return custom_urls + urls

    def status_display(self, obj):
        """状态显示（带颜色）"""
        status_colors = {
            CourtSMSStatus.PENDING: "orange",
            CourtSMSStatus.PARSING: "blue",
            CourtSMSStatus.DOWNLOADING: "blue",
            CourtSMSStatus.DOWNLOAD_FAILED: "red",
            CourtSMSStatus.MATCHING: "blue",
            CourtSMSStatus.PENDING_MANUAL: "orange",
            CourtSMSStatus.RENAMING: "blue",
            CourtSMSStatus.NOTIFYING: "blue",
            CourtSMSStatus.COMPLETED: "green",
            CourtSMSStatus.FAILED: "red",
        }
        color = status_colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = "处理状态"

    def sms_type_display(self, obj):
        """短信类型显示"""
        if not obj.sms_type:
            return "-"

        type_icons = {
            CourtSMSType.DOCUMENT_DELIVERY: "📄",
            CourtSMSType.INFO_NOTIFICATION: "📢",
            CourtSMSType.FILING_NOTIFICATION: "📋",
        }
        icon = type_icons.get(obj.sms_type, "❓")
        return f"{icon} {obj.get_sms_type_display()}"

    sms_type_display.short_description = "短信类型"

    def case_display(self, obj):
        """案件显示"""
        if obj.case:
            url = reverse("admin:cases_case_change", args=[obj.case.id])
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url,
                obj.case.name[:50] + ("..." if len(obj.case.name) > 50 else ""),
            )
        elif obj.status == CourtSMSStatus.PENDING_MANUAL:
            assign_url = reverse("admin:automation_courtsms_assign_case", args=[obj.id])
            return format_html('<a href="{}" style="color: orange; font-weight: bold;">🔗 手动指定案件</a>', assign_url)
        return "-"

    case_display.short_description = "关联案件"

    def content_preview(self, obj):
        """短信内容预览"""
        preview = obj.content[:100]
        if len(obj.content) > 100:
            preview += "..."
        return preview

    content_preview.short_description = "短信内容"

    def has_download_links(self, obj):
        """是否有下载链接"""
        if obj.download_links:
            return format_html('<span style="color: green;">✓ {} 个链接</span>', len(obj.download_links))
        return format_html('<span style="color: gray;">✗ 无链接</span>')

    has_download_links.short_description = "下载链接"

    def case_numbers_display(self, obj):
        """案号显示"""
        if obj.case_numbers:
            return mark_safe("<br>".join(obj.case_numbers))
        return "-"

    case_numbers_display.short_description = "提取的案号"

    def party_names_display(self, obj):
        """当事人显示"""
        if obj.party_names:
            return mark_safe("<br>".join(obj.party_names))
        return "-"

    party_names_display.short_description = "提取的当事人"

    def download_links_display(self, obj):
        """下载链接显示"""
        if obj.download_links:
            links_html = []
            for i, link in enumerate(obj.download_links, 1):
                links_html.append(f'<p><strong>链接 {i}:</strong><br><a href="{link}" target="_blank">{link}</a></p>')
            return mark_safe("".join(links_html))
        return "-"

    download_links_display.short_description = "下载链接"

    def scraper_task_link(self, obj):
        """爬虫任务链接"""
        if obj.scraper_task:
            url = reverse("admin:automation_scrapertask_change", args=[obj.scraper_task.id])
            return format_html(
                '<a href="{}" target="_blank">任务 #{} - {}</a>',
                url,
                obj.scraper_task.id,
                obj.scraper_task.get_status_display(),
            )
        return "-"

    scraper_task_link.short_description = "下载任务"

    def case_log_link(self, obj):
        """案件日志链接"""
        if obj.case_log:
            url = reverse("admin:cases_caselog_change", args=[obj.case_log.id])
            return format_html('<a href="{}" target="_blank">日志 #{}</a>', url, obj.case_log.id)
        return "-"

    case_log_link.short_description = "案件日志"

    def documents_display(self, obj):
        """关联文书显示"""
        if obj.scraper_task and hasattr(obj.scraper_task, "documents"):
            documents = obj.scraper_task.documents.all()
            if documents:
                docs_html = []
                for doc in documents:
                    status_color = {
                        "success": "green",
                        "failed": "red",
                        "pending": "orange",
                        "downloading": "blue",
                    }.get(doc.download_status, "gray")

                    doc_url = reverse("admin:automation_courtdocument_change", args=[doc.id])
                    docs_html.append(
                        f'<p><a href="{doc_url}" target="_blank">{doc.c_wsmc}</a> '
                        f'<span style="color: {status_color};">({doc.get_download_status_display()})</span></p>'
                    )
                return mark_safe("".join(docs_html))
        return "-"

    documents_display.short_description = "关联文书"

    def feishu_status(self, obj):
        """飞书发送状态"""
        if obj.feishu_sent_at:
            # 发送成功，检查是否有额外的状态信息
            if obj.feishu_error and obj.feishu_error not in ["发送失败", ""]:
                # 有详细状态信息（如案件群聊成功等）
                return format_html(
                    '<span style="color: green;">✓ 通知成功</span><br>'
                    "<small>{}</small><br>"
                    '<small style="color: #666;">{}</small>',
                    obj.feishu_sent_at.strftime("%m-%d %H:%M"),
                    obj.feishu_error[:50] + ("..." if len(obj.feishu_error) > 50 else ""),
                )
            else:
                # 纯粹的发送成功
                return format_html(
                    '<span style="color: green;">✓ 通知成功</span><br><small>{}</small>',
                    obj.feishu_sent_at.strftime("%m-%d %H:%M"),
                )
        elif obj.feishu_error:
            # 发送失败
            error_preview = obj.feishu_error[:30] + ("..." if len(obj.feishu_error) > 30 else "")
            return format_html(
                '<span style="color: red;">✗ 通知失败</span><br><small style="color: #d63384;">{}</small>',
                error_preview,
            )
        return format_html('<span style="color: gray;">- 未发送</span>')

    feishu_status.short_description = "通知状态"

    def feishu_details(self, obj):
        """飞书详情"""
        if obj.feishu_sent_at:
            return f"发送时间: {obj.feishu_sent_at}"
        elif obj.feishu_error:
            return f"发送失败: {obj.feishu_error}"
        return "未发送"

    feishu_details.short_description = "飞书通知详情"

    def retry_button(self, obj):
        """重新处理按钮"""
        if obj.id:
            retry_url = reverse("admin:automation_courtsms_retry", args=[obj.id])
            return format_html(
                '<a href="{}" class="button" onclick="return confirm('
                "'确认要重新处理这条短信吗？这将重置状态并重新执行完整流程。');"
                '">'
                "🔄 重新处理</a>",
                retry_url,
            )
        return "-"

    retry_button.short_description = "操作"

    def retry_processing_action(self, request, queryset):
        """重新处理操作"""
        service = _get_court_sms_service()
        success_count = 0
        error_count = 0

        for sms in queryset:
            try:
                service.retry_processing(sms.id)
                success_count += 1
                logger.info(f"管理员重新处理短信: SMS ID={sms.id}, User={request.user}")
            except Exception as e:
                error_count += 1
                logger.error(f"管理员重新处理短信失败: SMS ID={sms.id}, 错误: {e!s}")

        if success_count > 0:
            messages.success(request, f"成功重新处理 {success_count} 条短信")
        if error_count > 0:
            messages.error(request, f"重新处理失败 {error_count} 条短信")

    retry_processing_action.short_description = "🔄 重新处理选中的短信"

    def submit_sms_view(self, request):
        """短信提交页面"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            received_at = request.POST.get("received_at")

            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()

                    # 处理收到时间
                    received_datetime = None
                    if received_at:
                        from django.utils.dateparse import parse_datetime

                        received_datetime = parse_datetime(received_at)

                    # 提交短信
                    sms = service.submit_sms(content, received_datetime)

                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    logger.info(f"管理员提交短信: SMS ID={sms.id}, User={request.user}")

                    # 跳转到短信详情页
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))

                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
                    logger.error(f"管理员提交短信失败: User={request.user}, 错误: {e!s}")

        # 获取最近的短信记录
        recent_sms = CourtSMS.objects.order_by("-created_at")[:10]

        context = {
            "title": "提交法院短信",
            "recent_sms": recent_sms,
            "opts": self.model._meta,
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/submit_sms.html", context)

    def _get_suggested_cases(self, sms: Any, case_service: Any, sms_id: int) -> list[Any]:
        """获取推荐案件"""
        suggested_cases: list[Any] = []
        try:
            if sms.party_names:
                for party_name in sms.party_names:
                    if party_name.strip():
                        suggested_cases.extend(case_service.search_cases_by_party_internal([party_name.strip()])[:5])
            if sms.case_numbers:
                for case_number in sms.case_numbers:
                    if case_number.strip():
                        suggested_cases.extend(case_service.search_cases_by_case_number_internal(case_number.strip())[:5])
            seen_ids: set[int] = set()
            unique: list[Any] = []
            for case in suggested_cases:
                if hasattr(case, "id") and case.id not in seen_ids:
                    seen_ids.add(case.id)
                    unique.append(case)
            return unique[:10]
        except Exception as e:
            logger.warning(f"获取推荐案件失败: SMS ID={sms_id}, 错误: {e!s}")
            return []

    def _get_recent_cases(self, case_service: Any, sms_id: int) -> list[Any]:
        """获取最近案件"""
        try:
            all_recent = case_service.search_cases_by_party_internal([])
            return all_recent[:20] if all_recent else []
        except Exception as e:
            logger.warning(f"获取最近案件失败: SMS ID={sms_id}, 错误: {e!s}")
            return []

    def _format_case_for_template(self, case_dto: Any) -> dict[str, Any]:
        """将 CaseDTO 转换为模板可用的格式"""
        try:
            case_service = _get_case_service()
            case_detail = case_service.get_case_detail_internal(case_dto.id)
            return {
                "id": case_detail.id,
                "name": case_detail.name,
                "created_at": case_detail.created_at,
                "case_numbers": getattr(case_detail, "case_numbers", []),
                "parties": getattr(case_detail, "parties", []),
            }
        except Exception as e:
            logger.warning(f"格式化案件数据失败: Case ID={case_dto.id}, 错误: {e!s}")
            return {"id": case_dto.id, "name": case_dto.name, "created_at": None, "case_numbers": [], "parties": []}

    def assign_case_view(self, request: Any, sms_id: int) -> Any:
        """手动指定案件页面"""
        sms = get_object_or_404(CourtSMS, id=sms_id)

        if request.method == "POST":
            case_id = request.POST.get("case_id")
            if not case_id:
                messages.error(request, "请选择一个案件")
            else:
                try:
                    service = _get_court_sms_service()
                    service.assign_case(sms_id, int(case_id))
                    messages.success(request, "案件指定成功！已触发文书重命名和推送通知流程")
                    logger.info(f"管理员手动指定案件: SMS ID={sms_id}, Case ID={case_id}, User={request.user}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))
                except Exception as e:
                    messages.error(request, f"指定案件失败: {e!s}")
                    logger.error(f"管理员手动指定案件失败: SMS ID={sms_id}, Case ID={case_id}, 错误: {e!s}")

        case_service = _get_case_service()
        suggested_cases = self._get_suggested_cases(sms, case_service, sms_id)
        recent_cases = self._get_recent_cases(case_service, sms_id)

        context = {
            "title": f"为短信 #{sms_id} 指定案件",
            "sms": sms,
            "suggested_cases": [self._format_case_for_template(c) for c in suggested_cases],
            "recent_cases": [self._format_case_for_template(c) for c in recent_cases],
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return render(request, "admin/automation/courtsms/assign_case.html", context)

    def search_cases_ajax(self, request, sms_id):
        """AJAX 案件搜索接口"""
        from django.http import JsonResponse

        if request.method != "GET":
            return JsonResponse({"error": "只支持 GET 请求"}, status=405)

        search_term = request.GET.get("q", "").strip()
        if not search_term:
            return JsonResponse({"cases": []})

        try:
            case_service = _get_case_service()

            # 搜索案件（限制结果数量）
            found_cases = []

            # 按当事人名称搜索
            party_cases = case_service.search_cases_by_party_internal([search_term])[:10]
            found_cases.extend(party_cases)

            # 按案号搜索
            number_cases = case_service.search_cases_by_case_number_internal(search_term)[:10]
            found_cases.extend(number_cases)

            # 去重
            seen_ids = set()
            unique_cases = []
            for case in found_cases:
                if hasattr(case, "id") and case.id not in seen_ids:
                    seen_ids.add(case.id)
                    unique_cases.append(case)

            # 限制总数
            unique_cases = unique_cases[:15]

            # 转换为 JSON 格式
            cases_data = []
            for case_dto in unique_cases:
                try:
                    case_service = _get_case_service()
                    case_detail = case_service.get_case_detail_internal(case_dto.id)

                    # 从 DTO 中提取案号和当事人信息
                    case_numbers = getattr(case_detail, "case_numbers", [])
                    parties = getattr(case_detail, "parties", [])

                    # 如果是列表对象，提取名称
                    if hasattr(case_numbers, "__iter__") and not isinstance(case_numbers, str):
                        case_numbers = [getattr(cn, "case_number", str(cn)) for cn in case_numbers]
                    if hasattr(parties, "__iter__") and not isinstance(parties, str):
                        parties = [getattr(party, "name", str(party)) for party in parties]

                    cases_data.append(
                        {
                            "id": case_detail.id,
                            "name": case_detail.name,
                            "case_numbers": case_numbers if isinstance(case_numbers, list) else [],
                            "parties": parties if isinstance(parties, list) else [],
                            "created_at": (
                                case_detail.created_at.strftime("%Y-%m-%d %H:%M") if case_detail.created_at else ""
                            ),
                        }
                    )
                except Exception as e:
                    logger.warning(f"格式化案件数据失败: Case ID={case_dto.id}, 错误: {e!s}")
                    continue

            return JsonResponse({"cases": cases_data})

        except Exception as e:
            logger.error(f"AJAX 搜索案件失败: SMS ID={sms_id}, 搜索词={search_term}, 错误: {e!s}")
            return JsonResponse({"error": "搜索失败，请重试"}, status=500)

    def retry_single_sms_view(self, request, sms_id):
        """单个短信重新处理"""
        get_object_or_404(CourtSMS, id=sms_id)

        try:
            service = _get_court_sms_service()
            service.retry_processing(sms_id)

            messages.success(request, f"短信 #{sms_id} 重新处理成功！")
            logger.info(f"管理员重新处理单个短信: SMS ID={sms_id}, User={request.user}")

        except Exception as e:
            messages.error(request, f"重新处理失败: {e!s}")
            logger.error(f"管理员重新处理单个短信失败: SMS ID={sms_id}, 错误: {e!s}")

        # 跳转回短信详情页
        return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms_id]))

    def get_search_results(self, request, queryset, search_term):
        """自定义搜索，支持 JSON 字段搜索"""
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)

        # 暂时禁用 JSON 字段搜索，因为 SQLite 不支持
        # 在生产环境中可以启用 PostgreSQL 的 JSON 搜索功能

        return queryset, may_have_duplicates

    def get_queryset(self, request):
        """优化查询性能"""
        return super().get_queryset(request).select_related("case", "scraper_task", "case_log")

    def get_fields(self, request, obj=None):
        """根据是否为新增页面返回不同的字段"""
        if obj is None:  # 新增页面
            return ["content", "received_at"]
        else:  # 编辑页面
            return [field.name for field in self.model._meta.fields if field.name != "id"]

    def get_readonly_fields(self, request, obj=None):
        """根据是否为新增页面返回不同的只读字段"""
        if obj is None:  # 新增页面
            return ["received_at"]  # 收到时间只读
        else:  # 编辑页面
            return self.readonly_fields

    def get_fieldsets(self, request, obj=None):
        """根据是否为新增页面返回不同的字段分组"""
        if obj is None:  # 新增页面
            return (
                (
                    "短信信息",
                    {
                        "fields": ("content", "received_at"),
                        "description": "请输入完整的法院短信内容。收到时间将自动设置为当前时间。",
                    },
                ),
            )
        else:  # 编辑页面
            return self.fieldsets

    def get_form(self, request, obj=None, **kwargs):
        """自定义表单"""
        form = super().get_form(request, obj, **kwargs)

        if obj is None:  # 新增页面
            # 设置收到时间的默认值为当前时间
            from django.utils import timezone

            # 安全地检查和设置 received_at 字段
            received_at_field = form.base_fields.get("received_at")
            if received_at_field:
                received_at_field.initial = timezone.now()
                received_at_field.help_text = "自动设置为当前时间，不可修改"

            # 安全地检查和设置 content 字段
            content_field = form.base_fields.get("content")
            if content_field:
                content_field.required = True
                content_field.help_text = "请粘贴完整的法院短信内容"
                # 安全地更新 widget 属性
                if hasattr(content_field, "widget") and hasattr(content_field.widget, "attrs"):
                    content_field.widget.attrs.update({"rows": 8, "placeholder": "请粘贴完整的法院短信内容..."})

        return form

    def save_model(self, request, obj, form, change):
        """保存模型时的处理"""
        if not change:  # 新增时
            # 确保收到时间不为空
            if not obj.received_at:
                from django.utils import timezone

                obj.received_at = timezone.now()

            # 自动触发处理流程
            super().save_model(request, obj, form, change)

            try:
                # 异步处理短信
                from django_q.tasks import async_task

                task_id = async_task(
                    "apps.automation.services.sms.court_sms_service.process_sms_async",
                    obj.id,
                    task_name=f"court_sms_processing_{obj.id}",
                )

                messages.success(request, f"短信已保存并开始处理！记录ID: {obj.id}")
                logger.info(f"管理员添加短信并触发处理: SMS ID={obj.id}, Task ID={task_id}, User={request.user}")

            except Exception as e:
                messages.warning(request, f"短信已保存，但处理任务启动失败: {e!s}")
                logger.error(f"管理员添加短信后处理任务启动失败: SMS ID={obj.id}, 错误: {e!s}")
        else:
            super().save_model(request, obj, form, change)

    def add2_view(self, request):
        """酷炫的短信添加页面"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()

            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    # 提交短信
                    sms = service.submit_sms(content, timezone.now())

                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    logger.info(f"管理员通过酷炫页面提交短信: SMS ID={sms.id}, User={request.user}")

                    # 跳转到短信详情页
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))

                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
                    logger.error(f"管理员通过酷炫页面提交短信失败: User={request.user}, 错误: {e!s}")

        # 获取最近的短信记录
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]

        context = {
            "title": "📱 添加法院短信",
            "recent_sms": recent_sms,
            "opts": self.model._meta,
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/add2.html", context)

    def add3_view(self, request):
        """极简玻璃拟态风格的短信添加页面"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()

            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    # 提交短信
                    sms = service.submit_sms(content, timezone.now())

                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    logger.info(f"管理员通过极简页面提交短信: SMS ID={sms.id}, User={request.user}")

                    # 跳转到短信详情页
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))

                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
                    logger.error(f"管理员通过极简页面提交短信失败: User={request.user}, 错误: {e!s}")

        # 获取最近的短信记录
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]

        context = {
            "title": "添加法院短信",
            "recent_sms": recent_sms,
            "opts": self.model._meta,
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/add3.html", context)

    def add4_view(self, request):
        """暗黑高科技风格的短信添加页面"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()

            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    # 提交短信
                    sms = service.submit_sms(content, timezone.now())

                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    logger.info(f"管理员通过高科技页面提交短信: SMS ID={sms.id}, User={request.user}")

                    # 跳转到短信详情页
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))

                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
                    logger.error(f"管理员通过高科技页面提交短信失败: User={request.user}, 错误: {e!s}")

        # 获取最近的短信记录
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]

        context = {
            "title": "法院短信终端",
            "recent_sms": recent_sms,
            "opts": self.model._meta,
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/add4.html", context)

    def add5_view(self, request):
        """日式禅意风格的短信添加页面"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()

            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    # 提交短信
                    sms = service.submit_sms(content, timezone.now())

                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    logger.info(f"管理员通过禅意页面提交短信: SMS ID={sms.id}, User={request.user}")

                    # 跳转到短信详情页
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))

                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
                    logger.error(f"管理员通过禅意页面提交短信失败: User={request.user}, 错误: {e!s}")

        # 获取最近的短信记录
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]

        context = {
            "title": "法院短信",
            "recent_sms": recent_sms,
            "opts": self.model._meta,
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/add5.html", context)

    def add6_view(self, request):
        """复古打字机报纸风格的短信添加页面"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()

            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    # 提交短信
                    sms = service.submit_sms(content, timezone.now())

                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    logger.info(f"管理员通过复古页面提交短信: SMS ID={sms.id}, User={request.user}")

                    # 跳转到短信详情页
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))

                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
                    logger.error(f"管理员通过复古页面提交短信失败: User={request.user}, 错误: {e!s}")

        # 获取最近的短信记录
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]

        context = {
            "title": "THE COURT SMS GAZETTE",
            "recent_sms": recent_sms,
            "opts": self.model._meta,
            "has_view_permission": True,
        }

        return render(request, "admin/automation/courtsms/add6.html", context)

    def add7_view(self, request):
        """赛博朋克霓虹风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add7.html",
            {"title": "NEON SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add8_view(self, request):
        """手绘涂鸦风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add8.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add9_view(self, request):
        """iOS风格卡片"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add9.html",
            {"title": "新建短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add10_view(self, request):
        """像素游戏风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add10.html",
            {"title": "PIXEL SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add11_view(self, request):
        """蒸汽朋克维多利亚机械风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add11.html",
            {
                "title": "STEAMWORK TELEGRAPH",
                "recent_sms": recent_sms,
                "opts": self.model._meta,
                "has_view_permission": True,
            },
        )

    def add12_view(self, request):
        """太空科幻风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add12.html",
            {"title": "SPACE COMMAND", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add13_view(self, request):
        """水墨中国风"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add13.html",
            {"title": "法院来函", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add14_view(self, request):
        """Material Design 3"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add14.html",
            {"title": "新建短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add15_view(self, request):
        """新拟态风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add15.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add16_view(self, request):
        """孟菲斯风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add16.html",
            {"title": "MEMPHIS SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add17_view(self, request):
        """极简北欧风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add17.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add18_view(self, request):
        """漫画波普风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add18.html",
            {"title": "POW! SMS!", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add19_view(self, request):
        """圣诞节日风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add19.html",
            {
                "title": "🎄 Holiday SMS",
                "recent_sms": recent_sms,
                "opts": self.model._meta,
                "has_view_permission": True,
            },
        )

    def add20_view(self, request):
        """海洋水下风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add20.html",
            {"title": "OCEAN SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add21_view(self, request):
        """森林自然风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add21.html",
            {"title": "森林信笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add22_view(self, request):
        """Art Deco 装饰艺术风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add22.html",
            {"title": "ART DECO SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add23_view(self, request):
        """Brutalist 野兽派风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add23.html",
            {"title": "BRUTAL SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add24_view(self, request):
        """Vaporwave 蒸汽波风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add24.html",
            {
                "title": "ＳＭＳ　ＷＡＶＥ",
                "recent_sms": recent_sms,
                "opts": self.model._meta,
                "has_view_permission": True,
            },
        )

    def add25_view(self, request):
        """Bauhaus 包豪斯风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add25.html",
            {"title": "BAUHAUS SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add26_view(self, request):
        """Gothic 哥特风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add26.html",
            {"title": "GOTHIC SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add27_view(self, request):
        """Kawaii 可爱风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add27.html",
            {"title": "✿ 可爱短信 ✿", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add28_view(self, request):
        """Grunge 垃圾摇滚风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add28.html",
            {"title": "GRUNGE SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add29_view(self, request):
        """Synthwave 合成波风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add29.html",
            {"title": "SYNTHWAVE SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add30_view(self, request):
        """Origami 折纸风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add30.html",
            {"title": "折纸信笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add31_view(self, request):
        """Chalkboard 黑板风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add31.html",
            {"title": "黑板短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add32_view(self, request):
        """青花瓷风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add32.html",
            {"title": "青花函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add33_view(self, request):
        """古籍竹简风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add33.html",
            {"title": "竹简函牍", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add34_view(self, request):
        """宫廷御用风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add34.html",
            {"title": "御用函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add35_view(self, request):
        """山水画卷风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add35.html",
            {"title": "山水函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add36_view(self, request):
        """红木书房风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add36.html",
            {"title": "书房函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add37_view(self, request):
        """敦煌壁画风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add37.html",
            {"title": "敦煌函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add38_view(self, request):
        """茶道禅意风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add38.html",
            {"title": "茶禅函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add39_view(self, request):
        """梅兰竹菊风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add39.html",
            {"title": "四君子函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add40_view(self, request):
        """古典园林风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add40.html",
            {"title": "园林函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add41_view(self, request):
        """金石篆刻风格"""
        if request.method == "POST":
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "短信内容不能为空")
            else:
                try:
                    service = _get_court_sms_service()
                    from django.utils import timezone

                    sms = service.submit_sms(content, timezone.now())
                    messages.success(request, f"短信提交成功！记录ID: {sms.id}")
                    return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[sms.id]))
                except Exception as e:
                    messages.error(request, f"提交失败: {e!s}")
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add41.html",
            {"title": "金石函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )
