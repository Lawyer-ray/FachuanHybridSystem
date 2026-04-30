"""扫描 MEDIA_ROOT 下没有数据库引用的孤儿文件。"""

from __future__ import annotations

import os
import time
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files.base import File
from django.core.management.base import BaseCommand, CommandParser
from django.db.models.fields.files import FieldFile


class Command(BaseCommand):
    help = "扫描 MEDIA_ROOT 下没有数据库引用的孤儿文件"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--delete",
            action="store_true",
            help="实际删除孤儿文件（默认只报告）",
        )
        parser.add_argument(
            "--older-than",
            type=int,
            default=0,
            metavar="DAYS",
            help="只处理修改时间超过 N 天的文件",
        )
        parser.add_argument(
            "--exclude-dirs",
            nargs="*",
            default=["tmp", "exports"],
            help="排除的目录名（默认: tmp exports）",
        )

    def handle(self, *args: object, **options: object) -> None:
        delete: bool = options["delete"]  # type: ignore[assignment]
        older_than: int = options["older_than"]  # type: ignore[assignment]
        exclude_dirs: list[str] = options["exclude_dirs"]  # type: ignore[assignment]

        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.is_dir():
            self.stderr.write(self.style.ERROR(f"MEDIA_ROOT 不存在: {media_root}"))
            return

        # 1. 收集数据库中所有 FileField/ImageField 引用的文件路径
        db_files = self._collect_db_file_paths(media_root)
        self.stdout.write(f"数据库引用文件数: {len(db_files)}")

        # 2. 扫描物理文件
        cutoff = time.time() - older_than * 86400 if older_than > 0 else 0
        orphan_files: list[Path] = []

        for dirpath, dirnames, filenames in os.walk(media_root):
            # 排除指定目录
            rel_dir = os.path.relpath(dirpath, media_root)
            top_level = rel_dir.split(os.sep)[0]
            if top_level in exclude_dirs:
                dirnames.clear()
                continue

            for fname in filenames:
                fpath = Path(dirpath) / fname
                rel_path = str(fpath.relative_to(media_root)).replace("\\", "/")

                # 检查是否在数据库引用中
                if rel_path in db_files:
                    continue

                # 检查文件年龄
                if cutoff > 0 and fpath.stat().st_mtime >= cutoff:
                    continue

                orphan_files.append(fpath)

        self.stdout.write(f"发现孤儿文件数: {len(orphan_files)}")

        if not orphan_files:
            self.stdout.write(self.style.SUCCESS("没有发现孤儿文件"))
            return

        total_size = 0
        for fpath in orphan_files:
            size = fpath.stat().st_size
            total_size += size
            rel_path = str(fpath.relative_to(media_root))
            if delete:
                try:
                    fpath.unlink()
                    self.stdout.write(self.style.WARNING(f"已删除: {rel_path} ({size} bytes)"))
                except OSError as e:
                    self.stderr.write(self.style.ERROR(f"删除失败: {rel_path} ({e})"))
            else:
                self.stdout.write(f"  {rel_path} ({size} bytes)")

        size_mb = total_size / (1024 * 1024)
        if delete:
            self.stdout.write(self.style.SUCCESS(f"已清理 {len(orphan_files)} 个孤儿文件，释放 {size_mb:.2f} MB"))
        else:
            self.stdout.write(self.style.WARNING(f"共 {len(orphan_files)} 个孤儿文件，占用 {size_mb:.2f} MB"))
            self.stdout.write("使用 --delete 参数实际删除")

    def _collect_db_file_paths(self, media_root: Path) -> set[str]:
        """遍历所有 Model，收集 FileField/ImageField 中存储的文件路径。"""
        db_files: set[str] = set()

        for model in apps.get_models():
            try:
                for field in model._meta.get_fields():
                    if not hasattr(field, "storage"):
                        continue
                    # FileField 或 ImageField
                    try:
                        for obj in model.objects.all().only(field.name):  # type: ignore[attr-defined]
                            field_file: FieldFile = getattr(obj, field.name)
                            if field_file and field_file.name:
                                name = field_file.name.replace("\\", "/")
                                db_files.add(name)
                    except Exception:
                        # 跳过查询失败的 Model（如数据库表不存在等）
                        continue
            except Exception:
                # 跳过 managed=False 等异常 Model
                continue

        return db_files
