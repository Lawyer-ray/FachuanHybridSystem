"""确保 CloakBrowser 浏览器二进制已安装（部署自检用）。

用法:  python apiSystem/manage.py ensure_cloakbrowser
安装失败时输出可操作的修复指引（而非一句 timed out）。
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.services.browser.launcher import CloakBrowserInstallError, ensure_browser_binary


class Command(BaseCommand):
    help = "确保 CloakBrowser 浏览器二进制已安装；失败时输出可操作的修复指引"

    def handle(self, *args: object, **options: object) -> None:
        try:
            path = ensure_browser_binary()
        except CloakBrowserInstallError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"CloakBrowser 就绪: {path}"))
