"""
导出当前数据库中的案由、法院和 LPR 利率数据为种子 JSON 文件

用于生成种子数据文件,提交到 Git 仓库供新用户使用.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "导出案由、法院、LPR 利率数据为种子 JSON 文件"

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--output-dir",
            type=str,
            default=None,
            help="输出目录（默认: 各 app 的 data/ 目录）",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        output_dir: str | None = options["output_dir"]

        if output_dir:
            core_dir = Path(output_dir)
            finance_dir = Path(output_dir)
            core_dir.mkdir(parents=True, exist_ok=True)
            finance_dir.mkdir(parents=True, exist_ok=True)
        else:
            core_dir = Path(__file__).resolve().parent.parent.parent / "data"
            finance_dir = Path(__file__).resolve().parent.parent.parent.parent / "finance" / "data"
            core_dir.mkdir(parents=True, exist_ok=True)
            finance_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write("📤 导出种子数据...")

        self._export_causes(core_dir)
        self._export_courts(core_dir)
        self._export_lpr(finance_dir)

        self.stdout.write(self.style.SUCCESS("完成！"))

    def _export_causes(self, output_dir: Path) -> None:
        from apps.core.models import CauseOfAction

        causes = CauseOfAction.objects.all().order_by("level", "code")
        count = causes.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("  ⚠️  案由: 表为空,跳过"))
            return

        data = []
        for c in causes:
            data.append(
                {
                    "code": c.code,
                    "name": c.name,
                    "case_type": c.case_type,
                    "parent_code": c.parent.code if c.parent else None,
                    "level": c.level,
                }
            )

        output_file = output_dir / "seed_causes_of_action.json"
        output_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"  ✅ 案由: {count} 条 → {output_file}"))

    def _export_courts(self, output_dir: Path) -> None:
        from apps.core.models import Court

        courts = Court.objects.all().order_by("level", "code")
        count = courts.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("  ⚠️  法院: 表为空,跳过"))
            return

        data = []
        for c in courts:
            data.append(
                {
                    "code": c.code,
                    "name": c.name,
                    "parent_code": c.parent.code if c.parent else None,
                    "level": c.level,
                    "province": c.province or "",
                }
            )

        output_file = output_dir / "seed_courts.json"
        output_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"  ✅ 法院: {count} 条 → {output_file}"))

    def _export_lpr(self, output_dir: Path) -> None:
        from apps.finance.models import LPRRate

        rates = LPRRate.objects.all().order_by("effective_date")
        count = rates.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("  ⚠️  LPR: 表为空,跳过"))
            return

        data = []
        for r in rates:
            data.append(
                {
                    "effective_date": str(r.effective_date),
                    "rate_1y": str(r.rate_1y),
                    "rate_5y": str(r.rate_5y),
                    "source": r.source or "",
                }
            )

        output_file = output_dir / "seed_lpr_rates.json"
        output_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"  ✅ LPR: {count} 条 → {output_file}"))
