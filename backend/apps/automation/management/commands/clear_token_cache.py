"""Django management command."""

from __future__ import annotations

"\nToken 缓存清理命令\n\n提供定向失效(推荐)与全量清理(高风险,受门禁控制).\n"
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.automation.services.token.cache_manager import TokenCacheManager


class Command(BaseCommand):
    help: str = "清理 token 缓存(支持定向失效与全量清理)"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--site", default=None, help="网站名称(定向失效时必填)")
        parser.add_argument("--account", action="append", default=[], help="账号(可重复传入,支持多账号)")
        parser.add_argument("--blacklist", action="store_true", default=False, help="同时失效黑名单缓存")
        parser.add_argument("--all", action="store_true", default=False, help="全量清理(高风险)")
        parser.add_argument("--execute", action="store_true", default=False, help="实际执行;不传则仅输出计划")

    def handle(self, *args, **options: Any) -> None:  # type: ignore[no-untyped-def]
        manager = TokenCacheManager()
        site = options.get("site") or None
        accounts: list[Any] = list(options.get("account") or [])
        do_blacklist = bool(options.get("blacklist"))
        do_all = bool(options.get("all"))
        execute = bool(options.get("execute"))
        if do_all and (site or accounts):
            raise CommandError("--all 不能与 --site/--account 同时使用")
        if not do_all and (not site):
            raise CommandError("定向失效需要提供 --site;或使用 --all 进行全量清理(高风险)")
        if not execute:
            self._print_plan(site=site, accounts=accounts, do_blacklist=do_blacklist, do_all=do_all)
            return
        if do_all:
            if not manager._is_cache_clear_allowed():
                raise CommandError("全量清理被门禁拒绝:仅 DEBUG 或 ALLOW_CACHE_CLEAR=true/1/yes 允许")
            manager.clear_all_cache()
            self.stdout.write(self.style.SUCCESS("已执行:全量清理 token 缓存"))
            return
        manager.invalidate_site_cache(site, accounts=accounts or None)  # type: ignore[arg-type]
        if do_blacklist:
            manager.invalidate_blacklist_cache()
        masked: list[Any] = []
        self.stdout.write(
            self.style.SUCCESS(
                f"已执行:site={site!r} credentials=1 token={len(accounts)} account_stats={len(accounts)}"
                + (f" accounts={masked!r}" if masked else "")
                + (" blacklist=1" if do_blacklist else "")
            )
        )

    def _print_plan(self, *, site: str | None, accounts: list[str], do_blacklist: bool, do_all: bool) -> None:
        if do_all:
            allow = (os.environ.get("ALLOW_CACHE_CLEAR", "") or "").lower() in ("true", "1", "yes")
            self.stdout.write("计划:全量清理 token 缓存(高风险)")
            self.stdout.write(f"门禁:DEBUG 或 ALLOW_CACHE_CLEAR=true/1/yes(当前 ALLOW_CACHE_CLEAR={allow})")
            self.stdout.write("执行方式:追加 --execute")
            return
        masked: list[Any] = []
        self.stdout.write("计划:定向失效 token 缓存")
        self.stdout.write(f"site={site!r}")
        self.stdout.write(f"失效:credentials=1 token={len(accounts)} account_stats={len(accounts)}")
        if masked:
            self.stdout.write(f"accounts={masked!r}")
        if do_blacklist:
            self.stdout.write("失效:blacklist=1")
        self.stdout.write("执行方式:追加 --execute")
