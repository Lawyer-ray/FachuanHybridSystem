"""把一个本地目录里的客户材料归案（附件 + 案件材料 + 解析任务）。

## 为什么是管理命令而不是接口

归案要读服务器/本机上的绝对路径，这不该暴露成 HTTP 能力；而律师手上真正要做的是
「这个案子还缺什么，缺的去补」。所以第一版先做成运维/律师助手可执行的命令，
接口层等权限模型（谁能对哪个案件执行归案）定下来再接。

用法：

    python manage.py ingest_case_materials --case-id 489 \
        --dir "/path/to/2-客户资料/2026.11.24-之前发律师函提供的材料"

幂等：同一案件同内容（SHA-256）的文件已登记就跳过，重复执行不会堆日志。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.cases.services.material.material_ingest_service import ingest_directory


class Command(BaseCommand):
    help = "把本地目录里的客户材料归案（附件 + 案件材料 + 解析任务），幂等"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--case-id", type=int, required=True, help="案件 ID")
        parser.add_argument("--dir", dest="directory", required=True, help="材料所在目录（绝对路径）")
        parser.add_argument("--type-name", default="客户提供材料", help="登记的材料类型名")
        parser.add_argument(
            "--no-parse",
            action="store_true",
            help="只登记不解析（大卷宗交给任务队列，或先看一眼文件清单）",
        )
        parser.add_argument("--backend", default="auto", help="解析后端：auto/mineru/deepseek/textin/local")

    def handle(self, *args: Any, **options: Any) -> None:
        directory = Path(str(options["directory"])).expanduser()
        if not directory.is_dir():
            raise CommandError(f"目录不存在: {directory}")
        materials = ingest_directory(
            case_id=int(options["case_id"]),
            directory=directory,
            material_type_name=str(options["type_name"]),
            parse_now=not bool(options["no_parse"]),
            backend=str(options["backend"]),
        )
        if not materials:
            self.stdout.write(self.style.WARNING("没有新登记的材料（全部已归案或文件不受支持）"))
            return
        for material in materials:
            task = getattr(material, "parsing_task", None)
            status = f"解析 #{task.pk}（{len(task.text or task.markdown or '')} 字）" if task else "未解析"
            self.stdout.write(f"  ✓ {material.source_attachment.original_filename} · {status}")
        self.stdout.write(self.style.SUCCESS(f"归案完成：{len(materials)} 份材料"))
