"""
法院短信 Admin 主题视图

包含 35+ 种不同风格的短信添加页面视图.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from apps.automation.models import CourtSMS

logger = logging.getLogger("apps.automation")


def _get_court_sms_service() -> Any:
    """获取法院短信服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_court_sms_service()


def _handle_themed_post(request: HttpRequest) -> HttpResponse | None:
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

    def add2_view(self, request: HttpRequest) -> HttpResponse:
        """酷炫的短信添加页面"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add2.html",
            {
                "title": "📱 添加法院短信",
                "recent_sms": recent_sms,
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_view_permission": True,
            },
        )

    def add3_view(self, request: HttpRequest) -> HttpResponse:
        """极简玻璃拟态风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add3.html",
            {"title": "添加法院短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add4_view(self, request: HttpRequest) -> HttpResponse:
        """暗黑高科技风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add4.html",
            {"title": "法院短信终端", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add5_view(self, request: HttpRequest) -> HttpResponse:
        """日式禅意风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add5.html",
            {"title": "法院短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add6_view(self, request: HttpRequest) -> HttpResponse:
        """复古打字机报纸风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response

        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add6.html",
            {
                "title": "THE COURT SMS GAZETTE",
                "recent_sms": recent_sms,
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_view_permission": True,
            },
        )

    def add7_view(self, request: HttpRequest) -> HttpResponse:
        """赛博朋克霓虹风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add7.html",
            {"title": "NEON SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add8_view(self, request: HttpRequest) -> HttpResponse:
        """手绘涂鸦风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add8.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add9_view(self, request: HttpRequest) -> HttpResponse:
        """iOS风格卡片"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add9.html",
            {"title": "新建短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add10_view(self, request: HttpRequest) -> HttpResponse:
        """像素游戏风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add10.html",
            {"title": "PIXEL SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add11_view(self, request: HttpRequest) -> HttpResponse:
        """蒸汽朋克维多利亚机械风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add11.html",
            {
                "title": "STEAMWORK TELEGRAPH",
                "recent_sms": recent_sms,
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_view_permission": True,
            },
        )

    def add12_view(self, request: HttpRequest) -> HttpResponse:
        """太空科幻风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add12.html",
            {"title": "SPACE COMMAND", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add13_view(self, request: HttpRequest) -> HttpResponse:
        """水墨中国风"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add13.html",
            {"title": "法院来函", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add14_view(self, request: HttpRequest) -> HttpResponse:
        """Material Design 3"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add14.html",
            {"title": "新建短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add15_view(self, request: HttpRequest) -> HttpResponse:
        """新拟态风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add15.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add16_view(self, request: HttpRequest) -> HttpResponse:
        """孟菲斯风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add16.html",
            {"title": "MEMPHIS SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add17_view(self, request: HttpRequest) -> HttpResponse:
        """极简北欧风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add17.html",
            {"title": "添加短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add18_view(self, request: HttpRequest) -> HttpResponse:
        """漫画波普风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add18.html",
            {"title": "POW! SMS!", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add19_view(self, request: HttpRequest) -> HttpResponse:
        """圣诞节日风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add19.html",
            {
                "title": "🎄 Holiday SMS",
                "recent_sms": recent_sms,
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_view_permission": True,
            },
        )

    def add20_view(self, request: HttpRequest) -> HttpResponse:
        """海洋水下风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add20.html",
            {"title": "OCEAN SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add21_view(self, request: HttpRequest) -> HttpResponse:
        """森林自然风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add21.html",
            {"title": "森林信笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add22_view(self, request: HttpRequest) -> HttpResponse:
        """Art Deco 装饰艺术风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add22.html",
            {"title": "ART DECO SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add23_view(self, request: HttpRequest) -> HttpResponse:
        """Brutalist 野兽派风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add23.html",
            {"title": "BRUTAL SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add24_view(self, request: HttpRequest) -> HttpResponse:
        """Vaporwave 蒸汽波风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add24.html",
            {
                "title": "ＳＭＳ　ＷＡＶＥ",
                "recent_sms": recent_sms,
                "opts": self.model._meta,  # type: ignore[attr-defined]
                "has_view_permission": True,
            },
        )

    def add25_view(self, request: HttpRequest) -> HttpResponse:
        """Bauhaus 包豪斯风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add25.html",
            {"title": "BAUHAUS SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add26_view(self, request: HttpRequest) -> HttpResponse:
        """Gothic 哥特风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add26.html",
            {"title": "GOTHIC SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add27_view(self, request: HttpRequest) -> HttpResponse:
        """Kawaii 可爱风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add27.html",
            {"title": "✿ 可爱短信 ✿", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add28_view(self, request: HttpRequest) -> HttpResponse:
        """Grunge 垃圾摇滚风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add28.html",
            {"title": "GRUNGE SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add29_view(self, request: HttpRequest) -> HttpResponse:
        """Synthwave 合成波风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add29.html",
            {"title": "SYNTHWAVE SMS", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add30_view(self, request: HttpRequest) -> HttpResponse:
        """Origami 折纸风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add30.html",
            {"title": "折纸信笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add31_view(self, request: HttpRequest) -> HttpResponse:
        """Chalkboard 黑板风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add31.html",
            {"title": "黑板短信", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add32_view(self, request: HttpRequest) -> HttpResponse:
        """青花瓷风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add32.html",
            {"title": "青花函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add33_view(self, request: HttpRequest) -> HttpResponse:
        """古籍竹简风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add33.html",
            {"title": "竹简函牍", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add34_view(self, request: HttpRequest) -> HttpResponse:
        """宫廷御用风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add34.html",
            {"title": "御用函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add35_view(self, request: HttpRequest) -> HttpResponse:
        """山水画卷风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add35.html",
            {"title": "山水函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add36_view(self, request: HttpRequest) -> HttpResponse:
        """红木书房风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add36.html",
            {"title": "书房函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add37_view(self, request: HttpRequest) -> HttpResponse:
        """敦煌壁画风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add37.html",
            {"title": "敦煌函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add38_view(self, request: HttpRequest) -> HttpResponse:
        """茶道禅意风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add38.html",
            {"title": "茶禅函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add39_view(self, request: HttpRequest) -> HttpResponse:
        """梅兰竹菊风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add39.html",
            {"title": "四君子函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add40_view(self, request: HttpRequest) -> HttpResponse:
        """古典园林风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add40.html",
            {"title": "园林函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )

    def add41_view(self, request: HttpRequest) -> HttpResponse:
        """金石篆刻风格"""
        if request.method == "POST":
            response = _handle_themed_post(request)
            if response:
                return response
        recent_sms = CourtSMS.objects.order_by("-created_at")[:5]
        return render(
            request,
            "admin/automation/courtsms/add41.html",
            {"title": "金石函笺", "recent_sms": recent_sms, "opts": self.model._meta, "has_view_permission": True},  # type: ignore[attr-defined]
        )
