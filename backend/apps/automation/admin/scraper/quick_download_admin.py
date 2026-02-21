"""
快速下载文书 Admin
提供一个简单的表单，快速创建文书下载任务
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.urls import URLPattern, path, reverse
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from apps.automation.models import NamerTool, ScraperTask, ScraperTaskType


class QuickDownloadTool(NamerTool):
    class Meta:
        proxy = True
        managed = False
        app_label = "automation"
        verbose_name = _("快速下载文书")
        verbose_name_plural = _("快速下载文书")


# @admin.register(QuickDownloadTool)  # 隐藏快速下载页面，保留功能代码
class QuickDownloadAdmin(admin.ModelAdmin[QuickDownloadTool]):
    """快速下载文书管理类"""

    change_list_template: ClassVar[str | None] = None

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom: list[URLPattern] = [
            path("download/", self.admin_site.admin_view(self.download_view), name="{}_{}_download".format(*info)),
            path("", self.admin_site.admin_view(self.redirect_to_download)),
        ]
        return custom + urls  # type: ignore[return-value]

    def redirect_to_download(self, request: HttpRequest) -> HttpResponseRedirect:
        info = self.model._meta.app_label, self.model._meta.model_name
        return HttpResponseRedirect(reverse("admin:{}_{}_download".format(*info)))

    def download_view(self, request: HttpRequest) -> HttpResponse:
        """快速下载主视图"""
        if request.method == "POST":
            return self._handle_post(request)
        return self._render_form(request)

    def _handle_post(self, request: HttpRequest) -> HttpResponse:
        """处理POST请求"""
        url = request.POST.get("url", "").strip()
        case_id = request.POST.get("case_id", "").strip()

        if not url:
            return self._render_form(request, error="请输入文书链接")

        if not ("zxfw.court.gov.cn" in url or "sd.gdems.com" in url):
            return self._render_form(request, error="不支持的链接格式，仅支持 zxfw.court.gov.cn 和 sd.gdems.com")

        try:
            task_data: dict[str, Any] = {
                "task_type": ScraperTaskType.COURT_DOCUMENT,
                "url": url,
                "priority": 3,
                "config": {},
            }

            if case_id:
                try:
                    task_data["case_id"] = int(case_id)
                except ValueError:
                    return self._render_form(request, error="案件 ID 必须是数字")

            task = ScraperTask.objects.create(**task_data)

            from django_q.tasks import async_task

            async_task("apps.automation.tasks.execute_scraper_task", task.id)

            return self._render_result(task)

        except Exception as e:
            return self._render_form(request, error=f"创建任务失败: {e!s}")

    def _render_form(self, request: HttpRequest, error: str | None = None) -> HttpResponse:
        """渲染下载表单"""
        csrf_token = get_token(request)
        error_html = f'<div class="error-msg">❌ {escape(error)}</div>' if error else ""

        recent_tasks = ScraperTask.objects.filter(task_type=ScraperTaskType.COURT_DOCUMENT).order_by("-created_at")[:10]

        tasks_html = ""
        for task in recent_tasks:
            status_color = {
                "pending": "#ffa500",
                "running": "#007bff",
                "success": "#28a745",
                "failed": "#dc3545",
            }.get(task.status, "#666")

            link_type = "zxfw" if "zxfw.court.gov.cn" in task.url else "gdems"
            link_icon = "⚖️" if link_type == "zxfw" else "📧"

            case_info = (
                f'<a href="/admin/cases/case/{task.case_id}/change/" target="_blank">{task.case.name}</a>'
                if task.case
                else "-"
            )

            tasks_html += f"""
            <tr>
                <td>{task.id}</td>
                <td>{link_icon} {link_type}</td>
                <td>{case_info}</td>
                <td style="color: {status_color}; font-weight: bold;">{task.get_status_display()}</td>
                <td>{task.created_at.strftime("%Y-%m-%d %H:%M:%S")}</td>
                <td>
                    <a href="/admin/automation/scrapertask/{task.id}/change/" target="_blank">查看详情</a>
                </td>
            </tr>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>快速下载文书</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
            sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px;
            border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a1a1a; margin-bottom: 8px; }}
        .subtitle {{ color: #666; margin-bottom: 24px; }}
        .form-group {{ margin-bottom: 20px; }}
        label {{ display: block; margin-bottom: 8px; font-weight: 600; color: #333; }}
        input[type="url"], input[type="number"] {{ width: 100%; padding: 12px;
            border: 2px solid #e0e0e0; border-radius: 8px; font-size: 14px; }}
        .btn {{ background: linear-gradient(135deg, #28a745, #20c997); color: white;
            padding: 14px 32px; border: none; border-radius: 8px; font-size: 16px;
            font-weight: 600; cursor: pointer; width: 100%; }}
        .btn:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(40,167,69,0.4); }}
        .error-msg {{ background: #fee; color: #c00; padding: 12px 16px; border-radius: 8px;
            margin-bottom: 20px; border-left: 4px solid #c00; }}
        .info-box {{ background: linear-gradient(135deg, #e7f3ff, #f0f7ff); padding: 16px;
            border-radius: 8px; margin-bottom: 24px; border-left: 4px solid #007bff; }}
        .info-box h3 {{ margin: 0 0 10px 0; color: #0056b3; font-size: 14px; }}
        .info-box ul {{ margin: 0; padding-left: 18px; color: #444; font-size: 13px;
            line-height: 1.6; }}
        .link-examples {{ background: #f8f9fa; padding: 12px; border-radius: 6px;
            margin-top: 8px; font-size: 12px; color: #666; }}
        .link-examples code {{ background: white; padding: 2px 6px; border-radius: 3px;
            font-family: monospace; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ 快速下载文书</h1>
        <p class="subtitle">粘贴法院发送的链接，一键下载司法文书</p>

        {error_html}

        <div class="info-box">
            <h3>💡 支持的链接类型</h3>
            <ul>
                <li><strong>⚖️ zxfw.court.gov.cn</strong> - 法院执行平台（可能包含多份文书）</li>
                <li><strong>📧 sd.gdems.com</strong> - 广东电子送达（打包下载 ZIP）</li>
            </ul>
            <div class="link-examples">
                <strong>示例链接：</strong><br>
                <code>https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=xxx...</code><br>
                <code>https://sd.gdems.com/v3/dzsd/B0MBNGh</code>
            </div>
        </div>

        <form method="post">
            <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}" />

            <div class="form-group">
                <label>🔗 文书链接 *</label>
                <input type="url" name="url" placeholder="粘贴法院发送的链接" required />
            </div>

            <div class="form-group">
                <label>📁 关联案件 ID（可选）</label>
                <input type="number" name="case_id" placeholder="如果知道案件 ID，可以填写" />
            </div>

            <button type="submit" class="btn">🚀 立即下载</button>
        </form>

        <h2 style="margin-top: 40px;">最近的下载任务</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>类型</th>
                    <th>案件</th>
                    <th>状态</th>
                    <th>创建时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {
            tasks_html if tasks_html else '<tr><td colspan="6" style="text-align:center;color:#999;">暂无任务</td></tr>'
        }
            </tbody>
        </table>
    </div>
</body>
</html>"""
        return HttpResponse(html)

    def _render_result(self, task: ScraperTask) -> HttpResponse:
        """渲染任务创建结果"""
        link_type = "zxfw.court.gov.cn" if "zxfw.court.gov.cn" in task.url else "sd.gdems.com"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>任务已创建</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
            sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }}
        .container {{ max-width: 600px; margin: 50px auto; background: white; padding: 40px;
            border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); text-align: center; }}
        .success-icon {{ font-size: 64px; margin-bottom: 20px; }}
        h1 {{ color: #28a745; margin-bottom: 16px; }}
        .task-id {{ font-size: 24px; color: #007bff; font-weight: bold; margin: 20px 0; }}
        .info {{ background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 20px 0; text-align: left; }}
        .info-item {{ margin: 8px 0; color: #666; }}
        .info-item strong {{ color: #333; }}
        .btn {{ display: inline-block; background: #007bff; color: white;
            padding: 12px 24px; border-radius: 8px; text-decoration: none; margin: 10px; }}
        .btn:hover {{ background: #0056b3; }}
        .btn-secondary {{ background: #6c757d; }}
        .btn-secondary:hover {{ background: #5a6268; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <h1>下载任务已创建</h1>
        <p>任务正在后台执行中，请稍候查看结果...</p>
        <div class="task-id">任务 ID: {task.id}</div>

        <div class="info">
            <div class="info-item"><strong>链接类型:</strong> {link_type}</div>
            <div class="info-item"><strong>优先级:</strong> 高（3）</div>
            <div class="info-item"><strong>关联案件:</strong> {task.case.name if task.case else "无"}</div>
            <div class="info-item"><strong>预计耗时:</strong> 30-60 秒</div>
        </div>

        <div style="margin-top: 30px;">
            <a href="/admin/automation/scrapertask/{task.id}/change/" class="btn">查看任务详情</a>
            <a href="javascript:history.back()" class="btn btn-secondary">继续下载</a>
        </div>
    </div>
</body>
</html>"""
        return HttpResponse(html)
