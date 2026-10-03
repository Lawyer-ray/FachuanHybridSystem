from __future__ import annotations

from django.template.loader import render_to_string
from django.utils import timezone

from apps.legal_solution.models import SolutionTask
from apps.legal_solution.services.solution_generator import sanitize_report_html


class HtmlRenderer:
    def render(self, task: SolutionTask) -> str:
        sections = list(task.sections.order_by("order"))
        for section in sections:
            # 兜底消毒：新数据落库前已消毒，此处覆盖存量未消毒数据与 admin 重新组装链路
            if section.html_content:
                section.html_content = sanitize_report_html(section.html_content)
        return render_to_string(
            "legal_solution/report.html",
            {
                "task": task,
                "sections": sections,
                "generated_at": timezone.localtime(timezone.now()).strftime("%Y年%m月%d日 %H:%M"),
            },
        )
