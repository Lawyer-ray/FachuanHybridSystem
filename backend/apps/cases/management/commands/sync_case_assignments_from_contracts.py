"""Django management command."""

from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help: str = "将已关联合同的案件律师指派与合同律师指派对齐"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--contract-id", type=int, default=None, help="仅同步指定合同 ID 的关联案件")
        parser.add_argument("--case-id", type=int, default=None, help="仅同步指定案件 ID")
        parser.add_argument("--dry-run", action="store_true", help="只统计,不写入")

    def handle(self, *args, **options: Any) -> None:  # type: ignore[override]
        contract_id = options["contract_id"]
        case_id = options["case_id"]
        dry_run = bool(options["dry_run"])
        from apps.cases.models import Case
        from apps.cases.services import CaseAssignmentService
        from apps.core.interfaces import ServiceLocator

        qs = Case.objects.filter(contract_id__isnull=False).only("id", "contract_id")
        if contract_id:
            qs = qs.filter(contract_id=contract_id)
        if case_id:
            qs = qs.filter(id=case_id)
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("未找到需要同步的案件"))
            return
        self.stdout.write(f"待同步案件数: {total}")
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run 模式:不会写入数据库"))
            return
        service = CaseAssignmentService(
            case_service=ServiceLocator.get_case_service(),
            contract_assignment_query_service=ServiceLocator.get_contract_assignment_query_service(),
        )  # type: ignore[call-arg]
        created_total = 0
        deleted_total = 0
        for case in qs.iterator(chunk_size=200):
            stats = service.sync_assignments_from_contract(case_id=case.id, user=None, perm_open_access=True)  # type: ignore[arg-type]
            created_total += int(stats.get("created", 0))
            deleted_total += int(stats.get("deleted", 0))
        self.stdout.write(self.style.SUCCESS("同步完成"))
        self.stdout.write(f"created: {created_total}, deleted: {deleted_total}")
