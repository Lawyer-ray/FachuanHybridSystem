"""清理误抓的页脚导航页（联系我们/隐私保护/免责声明/网站地图/使用帮助等）。

这些页面与真实文书共用 ``content/post_`` 路径，但位于 ``/wzdh/...`` 等
非列表目录下，不属于仲裁裁决书。本命令删除「detail_url 不在其来源列表目录内」
的文书记录（含其图片），不影响真实文书。

用法：
    python manage.py purge_labor_arbitration_nav --dry-run   # 仅预览
    python manage.py purge_labor_arbitration_nav             # 实际删除
    python manage.py purge_labor_arbitration_nav --source 1  # 限定来源
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

from apps.labor_arbitration.models import ArbitrationDocument, ArbitrationDocumentSource


class Command(BaseCommand):
    help = "删除 detail_url 不在来源列表目录内的误抓导航页"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--source", type=int, default=None, help="限定来源 ID")
        parser.add_argument("--dry-run", action="store_true", help="只预览，不删除")

    def handle(self, *args: Any, **options: Any) -> None:
        src_qs = ArbitrationDocumentSource.objects.all()
        if options["source"]:
            src_qs = src_qs.filter(id=options["source"])
        if not src_qs.exists():
            raise CommandError("没有匹配的来源")

        to_delete: list[ArbitrationDocument] = []
        for src in src_qs:
            prefix = src.list_url
            prefix = prefix if prefix.endswith("/") else prefix + "/"
            base = urlparse(prefix)
            for doc in src.documents.all():
                cur = urlparse(doc.detail_url)
                in_dir = base.netloc == cur.netloc and cur.path.startswith(base.path)
                if not in_dir:
                    to_delete.append(doc)

        if not to_delete:
            self.stdout.write(self.style.SUCCESS("没有需要清理的导航页记录。"))
            return

        self.stdout.write(f"将删除 {len(to_delete)} 条导航页记录：")
        for doc in to_delete:
            self.stdout.write(f"  - [{doc.source.district}] {doc.title}  <{doc.detail_url}>")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("（dry-run 模式，未执行删除）"))
            return

        n = len(to_delete)
        for doc in to_delete:
            doc.delete()  # 级联删除图片（post_delete 信号清物理文件）
        self.stdout.write(self.style.SUCCESS(f"已删除 {n} 条导航页记录。"))
