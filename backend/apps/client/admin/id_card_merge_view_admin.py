"""
身份证合并独立视图

提供独立的上传界面,用户可以直接上传正反面图片进行合并
"""

import logging

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.html import format_html

logger = logging.getLogger("apps.client")


def _get_id_card_merge_service() -> None:
    """工厂函数:获取身份证合并服务"""
    from apps.client.services.id_card_merge_service import IdCardMergeService

    return IdCardMergeService()


@staff_member_required
def id_card_merge_view(request) -> None:
    """
    身份证合并视图

    GET: 显示上传表单
    POST: 处理上传并合并
    """
    context = {
        "title": "身份证合并",
        "site_header": admin.site.site_header,
        "site_title": admin.site.site_title,
        "has_permission": True,
    }

    if request.method == "POST":
        front_image = request.FILES.get("front_image")
        back_image = request.FILES.get("back_image")

        if not front_image:
            messages.error(request, "请上传身份证正面图片")
            return render(request, "admin/client/id_card_merge.html", context)

        if not back_image:
            messages.error(request, "请上传身份证反面图片")
            return render(request, "admin/client/id_card_merge.html", context)

        service = _get_id_card_merge_service()
        result = service.merge_id_card(front_image, back_image)

        if result.get("success"):
            pdf_url = result.get("pdf_url", "")
            context["success"] = True
            context["pdf_url"] = pdf_url
            messages.success(
                request,
                format_html('身份证合并成功!<a href="{}" target="_blank">点击下载 PDF</a>', pdf_url),
            )
        else:
            error = result.get("error", "UNKNOWN")
            message = result.get("message", "未知错误")

            if error == "AUTO_DETECT_FAILED":
                context["auto_detect_failed"] = True
                context["front_image_url"] = result.get("front_image_url", "")
                context["back_image_url"] = result.get("back_image_url", "")
                messages.warning(request, f"自动检测失败:{message}")
            else:
                messages.error(request, f"合并失败:{message}")

    return render(request, "admin/client/id_card_merge.html", context)


@staff_member_required
def id_card_merge_manual_view(request) -> None:
    """
    身份证手动合并视图

    POST: 处理手动指定四角坐标的合并
    """
    if request.method != "POST":
        return redirect("admin:id_card_merge")

    import json

    front_image_path = request.POST.get("front_image_path", "")
    back_image_path = request.POST.get("back_image_path", "")
    front_corners_str = request.POST.get("front_corners", "")
    back_corners_str = request.POST.get("back_corners", "")

    try:
        front_corners = json.loads(front_corners_str)
        back_corners = json.loads(back_corners_str)
    except json.JSONDecodeError:
        messages.error(request, "四角坐标格式错误,请输入有效的 JSON 数组")
        return redirect("admin:id_card_merge")

    service = _get_id_card_merge_service()
    result = service.merge_id_card_manual(
        front_image_path=front_image_path,
        back_image_path=back_image_path,
        front_corners=front_corners,
        back_corners=back_corners,
    )

    if result.get("success"):
        pdf_url = result.get("pdf_url", "")
        messages.success(
            request,
            format_html('身份证合并成功!<a href="{}" target="_blank">点击下载 PDF</a>', pdf_url),
        )
    else:
        message = result.get("message", "未知错误")
        messages.error(request, f"合并失败:{message}")

    return redirect("admin:id_card_merge")


def get_id_card_merge_urls() -> None:
    """获取身份证合并相关的 URL 配置"""
    return [
        path(
            "client/id-card-merge/",
            admin.site.admin_view(id_card_merge_view),
            name="id_card_merge",
        ),
        path(
            "client/id-card-merge/manual/",
            admin.site.admin_view(id_card_merge_manual_view),
            name="id_card_merge_manual",
        ),
    ]


def register_id_card_merge_urls(admin_site) -> None:
    """注册身份证合并页面的 URL 到 admin site"""
    original_get_urls = admin_site.get_urls

    def get_urls() -> None:
        urls = original_get_urls()
        custom_urls = [
            path(
                "client/id-card-merge/",
                admin_site.admin_view(id_card_merge_view),
                name="id_card_merge",
            ),
            path(
                "client/id-card-merge/manual/",
                admin_site.admin_view(id_card_merge_manual_view),
                name="id_card_merge_manual",
            ),
        ]
        return custom_urls + urls

    admin_site.get_urls = get_urls


register_id_card_merge_urls(admin.site)
