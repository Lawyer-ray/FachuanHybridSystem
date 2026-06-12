"""创建测试用工作流模板"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.workflow.models import WorkflowTemplate


class Command(BaseCommand):
    help = "创建测试用工作流模板"

    def handle(self, *args: Any, **options: Any) -> None:
        template, created = WorkflowTemplate.objects.update_or_create(
            slug="sales-contract-dispute-test",
            defaults={
                "name": "买卖合同纠纷(测试)",
                "category": WorkflowTemplate.Category.LITIGATION,
                "description": "测试用简化流程：收集事实 → 确认 → 生成起诉状 → 审批 → 完成",
                "temporal_workflow_name": "SalesContractDisputeWorkflow",
                "steps_schema": [
                    {"id": "collect_facts", "name": "收集案件事实", "type": "activity", "timeout": "30s", "retry_max": 3, "on_fail": "abort"},
                    {"id": "confirm_facts", "name": "确认事实", "type": "gate", "signal_key": "confirm_facts_approved"},
                    {"id": "draft_complaint", "name": "生成起诉状", "type": "activity", "timeout": "5m", "retry_max": 2, "on_fail": "abort"},
                    {"id": "review_complaint", "name": "审批起诉状", "type": "gate", "signal_key": "review_complaint_approved"},
                ],
                "is_active": True,
            },
        )
        action = "创建" if created else "更新"
        self.stdout.write(self.style.SUCCESS(f"{action}模板: {template.name} (slug={template.slug})"))
