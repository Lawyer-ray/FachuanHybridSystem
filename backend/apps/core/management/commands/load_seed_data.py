"""
加载种子数据到数据库

从 JSON 种子文件加载案由、法院和 LPR 利率数据.
默认仅在表为空时加载;使用 --force 强制重新加载.
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "加载种子数据（案由、法院、LPR利率）到数据库"

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--force",
            action="store_true",
            help="强制重新加载（清空已有数据）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="预览模式,不实际写入数据库",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        force: bool = options["force"]
        dry_run: bool = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 预览模式 — 不会写入数据库"))
            self._dry_run()
            return

        self.stdout.write("📋 加载种子数据...")

        from apps.core.services.seed_data_loader import load_cause_seed_data, load_court_seed_data
        from apps.finance.services.lpr.seed_data_loader import load_lpr_seed_data

        # 案由
        result = load_cause_seed_data(force=force)
        if result["skipped"]:
            self.stdout.write(self.style.NOTICE("  ⏭️  案由: 表非空,跳过（使用 --force 强制）"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ✅ 案由: 加载 {result['loaded']} 条"))

        # 法院
        result = load_court_seed_data(force=force)
        if result["skipped"]:
            self.stdout.write(self.style.NOTICE("  ⏭️  法院: 表非空,跳过（使用 --force 强制）"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ✅ 法院: 加载 {result['loaded']} 条"))

        # LPR
        result = load_lpr_seed_data(force=force)
        if result["skipped"]:
            self.stdout.write(self.style.NOTICE("  ⏭️  LPR: 表非空,跳过（使用 --force 强制）"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ✅ LPR: 加载 {result['loaded']} 条"))

        self.stdout.write(self.style.SUCCESS("完成！"))

    def _dry_run(self) -> None:
        """预览种子数据,不写入数据库."""
        import json
        from pathlib import Path

        core_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        finance_data_dir = Path(__file__).resolve().parent.parent.parent.parent / "finance" / "data"

        for label, path in [
            ("案由", core_data_dir / "seed_causes_of_action.json"),
            ("法院", core_data_dir / "seed_courts.json"),
            ("LPR", finance_data_dir / "seed_lpr_rates.json"),
        ]:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self.stdout.write(f"  📄 {label}: {len(data)} 条 ({path})")
            else:
                self.stdout.write(self.style.WARNING(f"  ⚠️  {label}: 文件不存在 ({path})"))
