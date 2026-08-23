"""爬取佛山劳动仲裁文书（命令行触发，便于测试与 CI）。

用法：
    python manage.py crawl_labor_arbitration --all
    python manage.py crawl_labor_arbitration --source 1 --limit 3
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.labor_arbitration.models import ArbitrationDocumentSource
from apps.labor_arbitration.services.crawler import FoshanLaborAwardCrawler


class Command(BaseCommand):
    help = "爬取佛山劳动仲裁文书（支持 --source / --all / --limit）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--source", type=int, help="来源 ID")
        parser.add_argument("--all", action="store_true", help="爬取全部启用来源")
        parser.add_argument("--limit", type=int, default=None, help="每个来源最多处理的条目数")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["source"]:
            qs = ArbitrationDocumentSource.objects.filter(id=options["source"])
        elif options["all"]:
            qs = ArbitrationDocumentSource.objects.filter(enabled=True)
        else:
            raise CommandError("请指定 --source <id> 或 --all")

        if not qs.exists():
            raise CommandError("没有匹配的来源")

        for src in qs:
            self.stdout.write(f"爬取来源: {src.name} ({src.list_url})")
            try:
                crawler = FoshanLaborAwardCrawler(src, limit=options["limit"])
                stats = crawler.crawl()
                self.stdout.write(self.style.SUCCESS(f"结果: {stats}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"失败: {exc}"))
