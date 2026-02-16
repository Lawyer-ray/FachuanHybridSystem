"""Django management command."""

from django.core.management.base import BaseCommand

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec


class Command(BaseCommand):
    help: str = "加密存量 SystemConfig 中 is_secret=True 的明文值"

    def handle(self, *args, **options) -> None:
        codec = SecretCodec()
        qs = SystemConfig.objects.filter(is_secret=True, is_active=True).exclude(value="").exclude(value__isnull=True)
        to_encrypt = [c for c in qs if not codec.is_encrypted(c.value)]

        if not to_encrypt:
            self.stdout.write(self.style.SUCCESS("未发现需要加密的 SystemConfig secrets"))
            return

        updated = 0
        for c in to_encrypt:
            c.value = codec.encrypt(c.value)
            c.save(update_fields=["value", "updated_at"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"已加密 {updated} 条 SystemConfig secrets"))
