"""
法院短信 Admin 主题视图

包含 35+ 种不同风格的短信添加页面视图.
"""

import logging
from typing import Any, cast

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from apps.automation.models import CourtSMS

logger = logging.getLogger("apps.automation")


def _get_court_sms_service() -> None:
    """获取法院短信服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_court_sms_service()


def _handle_themed_post(request, sms_id_on_success) -> None:
    """处理主题视图的 POST 请求(通用逻辑)"""
    content = request.POST.get("content", "").strip()
    if not content:
        messages.error(request, "短信内容不能为空")
        return None

    try:
        service = _get_court_sms_service()
        from django.utils import timezone

        sms = service.submit_sms(content, timezone.now())
        messages.success(request, f"短信提交成功!记录ID: {sms.id}")
        return HttpResponseRedirect(reverse("admin:automation_courtsms_change", args=[cast(int, sms.id)]))
    except Exception as e:
        logger.exception("操作失败")
        messages.error(request, f"提交失败: {e!s}")
        return None


class CourtSMSAdminThemedViews:
    """法院短信 Admin 主题视图混入类"""

    def add2_view(self, request) -> None:
        """酷炫的短信添加页面"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add2.html",
            {
                "title": "📱 添加法院短信",
                "recent_sms": recent_sms,
                "opts": self.model._meta,
                "has_view_permission": True,
            },
        )

    def add3_view(self, request) -> None:
        """极简玻璃拟态风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add3.html",
            {"title": "添加法院短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add4_view(self, request) -> None:
        """暗黑高科技风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add4.html",
            {"title": "法院短信终端", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add5_view(self, request) -> None:
        """日式禅意风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add5.html",
            {"title": "法院短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add6_view(self, request) -> None:
        """复古打字机报纸风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add6.html",
            {
                "title": "THE COURT SMS GAZETTE",
                "recent_sms": recent_sms,
                "opts": self.model._meta,
                "has_view_permission": True,
            },
        )

    def add7_view(self, request) -> None:
        """赛博朋克霓虹风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add7.html",
            {"title": "NEON SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add8_view(self, request) -> None:
        """手绘涂鸦风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add8.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add9_view(self, request) -> None:
        """iOS风格卡片"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add9.html",
            {"title": "新建短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add10_view(self, request) -> None:
        """像素游戏风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add10.html",
            {"title": "PIXEL SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add11_view(self, request) -> None:
        """蒸汽朋克维多利亚机械风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
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

    def add12_view(self, request) -> None:
        """太空科幻风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add12.html",
            {"title": "SPACE COMMAND", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add13_view(self, request) -> None:
        """水墨中国风"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add13.html",
            {"title": "法院来函", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add14_view(self, request) -> None:
        """Material Design 3"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add14.html",
            {"title": "新建短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add15_view(self, request) -> None:
        """新拟态风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add15.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add16_view(self, request) -> None:
        """孟菲斯风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add16.html",
            {"title": "MEMPHIS SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add17_view(self, request) -> None:
        """极简北欧风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add17.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add18_view(self, request) -> None:
        """漫画波普风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add18.html",
            {"title": "POW! SMS!", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add19_view(self, request) -> None:
        """圣诞节日风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
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

    def add20_view(self, request) -> None:
        """海洋水下风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add20.html",
            {"title": "OCEAN SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add21_view(self, request) -> None:
        """森林自然风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add21.html",
            {"title": "森林信笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add22_view(self, request) -> None:
        """Art Deco 装饰艺术风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add22.html",
            {"title": "ART DECO SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add23_view(self, request) -> None:
        """Brutalist 野兽派风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add23.html",
            {"title": "BRUTAL SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add24_view(self, request) -> None:
        """Vaporwave 蒸汽波风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
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

    def add25_view(self, request) -> None:
        """Bauhaus 包豪斯风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add25.html",
            {"title": "BAUHAUS SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add26_view(self, request) -> None:
        """Gothic 哥特风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add26.html",
            {"title": "GOTHIC SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add27_view(self, request) -> None:
        """Kawaii 可爱风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add27.html",
            {"title": "✿ 可爱短信 ✿", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add28_view(self, request) -> None:
        """Grunge 垃圾摇滚风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add28.html",
            {"title": "GRUNGE SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add29_view(self, request) -> None:
        """Synthwave 合成波风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add29.html",
            {"title": "SYNTHWAVE SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add30_view(self, request) -> None:
        """Origami 折纸风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add30.html",
            {"title": "折纸信笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add31_view(self, request) -> None:
        """Chalkboard 黑板风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add31.html",
            {"title": "黑板短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add32_view(self, request) -> None:
        """青花瓷风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add32.html",
            {"title": "青花函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add33_view(self, request) -> None:
        """古籍竹简风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add33.html",
            {"title": "竹简函牍", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add34_view(self, request) -> None:
        """宫廷御用风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add34.html",
            {"title": "御用函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add35_view(self, request) -> None:
        """山水画卷风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add35.html",
            {"title": "山水函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add36_view(self, request) -> None:
        """红木书房风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add36.html",
            {"title": "书房函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add37_view(self, request) -> None:
        """敦煌壁画风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add37.html",
            {"title": "敦煌函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add38_view(self, request) -> None:
        """茶道禅意风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add38.html",
            {"title": "茶禅函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add39_view(self, request) -> None:
        """梅兰竹菊风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add39.html",
            {"title": "四君子函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add40_view(self, request) -> None:
        """古典园林风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add40.html",
            {"title": "园林函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )

    def add41_view(self, request) -> None:
        """金石篆刻风格"""
        if request.method == "POST":
            response = _handle_themed_post(request, None)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add41.html",
            {"title": "金石函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},
        )
