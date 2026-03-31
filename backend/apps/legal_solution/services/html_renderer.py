from __future__ import annotations

from django.template.loader import render_to_string
from django.utils import timezone

from apps.legal_solution.models import SolutionTask


class HtmlRenderer:
    def render(self, task: SolutionTask) -> str:
        sections = list(task.sections.order_by("order"))
        return render_to_string(
            "legal_solution/report.html",
            {
                "task": task,
                "sections": sections,
                "generated_at": timezone.localtime(timezone.now()).strftime("%Y年%m月%d日 %H:%M"),
            },
        )
