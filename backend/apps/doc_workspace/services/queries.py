"""API 层要用的**只读查询**集中在这里。

## 为什么单独一个模块

四层架构的守门（`tests/ci/structure/test_four_layer_architecture.py`）禁止 API 层
直接写 `Model.objects.filter(...)`：接口层只做「参数 → service → 响应」的翻译，
数据访问下沉，才能保证同一套房口径（租户/权限/软删）只有一处实现。

这里的函数刻意只做查询、不带业务判断——带判断的（状态迁移、落笔、统计）都在
`review_model` / `write_service` 里。
"""

from __future__ import annotations

from typing import Any

from ..models import Finding, FindingStatus, Playbook, ReviewRun


def get_playbook(playbook_id: int) -> Playbook | None:
    return Playbook.objects.filter(id=playbook_id).first()


def latest_run(*, kind: str, owner_id: int, subpath: str) -> ReviewRun | None:
    return (
        ReviewRun.objects.filter(owner_kind=kind, owner_id=owner_id, subpath=subpath)
        .order_by("-created_at", "-id")
        .first()
    )


def get_run(run_id: int) -> ReviewRun | None:
    return ReviewRun.objects.filter(id=run_id).first()


def get_finding(finding_id: int) -> Finding | None:
    return Finding.objects.filter(id=finding_id).select_related("run").first()


def proposed_findings(run: ReviewRun, *, severity: str = "", kinds: list[str] | None = None) -> list[Finding]:
    qs = Finding.objects.filter(run=run, status=FindingStatus.PROPOSED)
    if severity:
        qs = qs.filter(severity=severity)
    if kinds:
        qs = qs.filter(kind__in=kinds)
    return list(qs.select_related("run"))


def document_template_file(template_id: int) -> tuple[Any | None, str]:
    """取模板对象与它的磁盘路径（路径不可用时返回空串）。"""
    from pathlib import Path

    from apps.documents.models import DocumentTemplate

    template = DocumentTemplate.objects.filter(id=template_id).first()
    if template is None:
        return None, ""
    location = template.get_file_location()
    if not location or not Path(location).exists():
        return template, ""
    return template, str(location)


__all__ = [
    "document_template_file",
    "get_finding",
    "get_playbook",
    "get_run",
    "latest_run",
    "proposed_findings",
]
