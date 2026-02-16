"""Django management command."""
from apps.core.path import Path
from django.conf import settings
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help: str = '将 apps.client 内涉及文件的绝对路径统一归一化为 MEDIA_ROOT 相对路径'

    def handle(self, *args, **options) -> None:
        from apps.client.models import ClientIdentityDoc, PropertyClueAttachment
        root = Path(settings.MEDIA_ROOT).resolve()
        updated = 0
        skipped = 0

        def normalize(path_str: str) -> str | None:
            if not path_str:
                return None
            p = Path(path_str)
            if not p.is_absolute():
                return path_str.replace('\\', '/').lstrip('/') or None
            try:
                rel = p.resolve().relative_to(root)
            except ValueError:
                return None
            return str(rel).replace('\\', '/') or None
        updated, skipped = self._normalize_model_paths(ClientIdentityDoc, normalize, updated, skipped)
        updated, skipped = self._normalize_model_paths(PropertyClueAttachment, normalize, updated, skipped)
        self.stdout.write(self.style.SUCCESS(f'完成:更新 {updated} 条,跳过 {skipped} 条'))

    @staticmethod
    def _normalize_model_paths(model_class: Any, normalize_fn: Any, updated: Any, skipped: Any) -> None:
        for obj in model_class.objects.exclude(file_path='').iterator():
            new_path = normalize_fn(obj.file_path)
            if new_path is None:
                skipped += 1
                continue
            if new_path != obj.file_path:
                model_class.objects.filter(id=obj.id).update(file_path=new_path)
                updated += 1
        return (updated, skipped)