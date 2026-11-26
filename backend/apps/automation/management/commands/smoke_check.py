"""Django management command."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, cast
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.test import Client

from apps.core.infrastructure.subprocess_runner import SubprocessRunner
from apps.core.utils.path import Path

logger = logging.getLogger(__name__)


def smoke_q_task(a: int, b: int) -> int:
    return a + b


class _DummyAutoNamerService:
    def process_document_for_naming(
        self, uploaded_file: Any, prompt: Any, model: Any, limit: Any | None = None, preview_page: Any | None = None
    ) -> None:
        return {"text": "ok", "llm_response": {"filename": uploaded_file.name}, "error": None}  # type: ignore[return-value]


class _DummyDocumentProcessorService:
    def process_uploaded_document(
        self, uploaded_file: Any, limit: Any | None = None, preview_page: Any | None = None
    ) -> dict[str, Any]:
        return {
            "text": "ok",
            "image_url": None,
            "file_name": getattr(uploaded_file, "name", "unknown"),
            "file_size": getattr(uploaded_file, "size", None),
        }


class Command(BaseCommand):
    def __init__(self) -> None:
        super().__init__()
        # `--database-path` 真正切库后才置值；`_ensure_safe_target` / migrate 闸门都看它
        self._database_path: str | None = None

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--database-path", default=None)
        parser.add_argument(
            "--allow-migrate",
            action="store_true",
            default=False,
            help="显式允许执行 migrate（默认不跑：日志 P05-04 的「smoke_check 会跑 migrate」）",
        )
        parser.add_argument(
            "--skip-migrate",
            action="store_true",
            default=False,
            help="已废弃：migrate 现在默认不执行，本开关仅保留兼容旧调用",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            default=False,
            help="在非 DEBUG / 非测试库上确认执行（误在生产库上跑会在真库里建数据）",
        )
        parser.add_argument("--skip-admin", action="store_true", default=False)
        parser.add_argument("--skip-upload", action="store_true", default=False)
        parser.add_argument("--skip-websocket", action="store_true", default=False)
        parser.add_argument("--skip-q", action="store_true", default=False)
        parser.add_argument("--skip-capabilities", action="store_true", default=False)
        parser.add_argument("--skip-disk", action="store_true", default=False)
        parser.add_argument("--disk-warning-pct", type=float, default=85.0)
        parser.add_argument("--disk-critical-pct", type=float, default=95.0)

    def handle(self, *args, **options: Any) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
        self._database_path = None
        self._maybe_switch_sqlite_db(options.get("database_path"))
        self._ensure_safe_target(options)
        # migrate 只两种情况下跑（审计 P05-04）：显式 --allow-migrate，或目标是
        # 测试库/临时库（CI 与 make ci-backend 的 smoke 步骤依赖它建表）。
        if options.get("allow_migrate") or self._is_disposable_target():
            call_command("migrate", "--noinput", verbosity=0)
        user, created_smoke_user = self._ensure_smoke_superuser()
        try:
            client = Client()
            client.force_login(user)
            if not options.get("skip_admin"):
                self._check_admin_pages(client)
            if not options.get("skip_upload"):
                self._check_upload_endpoints(client)
            if not options.get("skip_websocket"):
                self._check_websocket(client, user)
            if not options.get("skip_q"):
                self._check_django_q()
            if not options.get("skip_capabilities"):
                self._check_deployment_capabilities()
            if not options.get("skip_disk"):
                self._check_disk_space(
                    warning_pct=options.get("disk_warning_pct", 85.0),
                    critical_pct=options.get("disk_critical_pct", 95.0),
                )
        finally:
            if created_smoke_user:
                self._cleanup_smoke_superuser(user)
        self.stdout.write(self.style.SUCCESS("✅ smoke_check 通过"))

    def _maybe_switch_sqlite_db(self, database_path: str | None) -> None:
        if not database_path:
            return
        default_db = settings.DATABASES.get("default", {})
        if default_db.get("ENGINE") != "django.db.backends.sqlite3":
            logger.info("smoke_check 忽略 --database-path: 当前数据库引擎不是 sqlite3")
            return
        db_path = Path(database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = str(db_path)
        settings.DATABASES["default"]["NAME"] = str(db_path)
        for conn in connections.all():
            conn.close()

    def _default_db_name(self) -> str:
        return str(settings.DATABASES.get("default", {}).get("NAME", ""))

    def _is_disposable_target(self) -> bool:
        """目标库是否「随便造也无所谓」：调用方指定的临时库，或库名带 test。

        ``--database-path`` 只在 sqlite 下真正生效（见 ``_maybe_switch_sqlite_db``），
        所以以 ``self._database_path`` 是否被置上为准——不能拿「传了这个参数」当已切库。
        """
        if self._database_path:
            return True
        return "test" in os.path.basename(self._default_db_name()).lower()

    def _ensure_safe_target(self, options: dict[str, Any]) -> None:
        """在真实（非 DEBUG、非测试）库上必须 ``--yes`` 才继续（审计 P05-04）。

        smoke_check 会建 superuser、登 admin 页面、打上传接口。旧实现无条件在
        ``settings.DATABASES["default"]`` 上跑 migrate + 建超管，误在生产库上执行等于
        往真实库里塞测试数据。

        不需要确认的情形：显式 ``--yes``；可丢弃的目标库（``--database-path`` 已生效的
        临时库、库名带 test）；``DEBUG`` 为真（开发库）。反过来说：**DEBUG 关且库名不像
        测试库**一定拦住。

        注：这里用「且」而非「或」——pytest 的 ``setup_test_environment()`` 会把 DEBUG
        强制置 False，测试库再要求 ``--yes`` 会让所有跑 ``call_command("smoke_check")`` 的
        既有测试一起变红；而「DEBUG 关 + 库名不像测试库」已经圈住了审计点名的真库误伤场景。
        """
        if options.get("yes"):
            return
        if self._is_disposable_target():
            return
        if settings.DEBUG:
            return

        raise CommandError(
            "smoke_check 拒绝在非 DEBUG / 非测试库上运行: DEBUG="
            f"{settings.DEBUG}, DB={self._default_db_name()!r}；确认无误请加 --yes"
        )

    def _ensure_smoke_superuser(self) -> tuple[Any, bool]:
        """返回 (smoke 用户, 是否本次新建)。新建的用户在命令结束时删除（安全审计 C-03）。"""
        User = get_user_model()
        username = "smoke_admin"
        user = User.objects.filter(username=username).first()
        if user:
            staff_user = cast(Any, user)
            if not bool(getattr(staff_user, "is_staff", False)):
                staff_user.is_staff = True
                staff_user.save(update_fields=["is_staff"])
            return staff_user, False
        # 口令只从 settings 读：以前这里有个内置默认口令 "smoke_admin_password"，
        # 等于把超管账号的密码写进了仓库（审计 P05-04）。缺配就拒绝执行。
        smoke_password = str(getattr(settings, "SMOKE_ADMIN_PASSWORD", "") or "").strip()
        if not smoke_password:
            raise CommandError("SMOKE_ADMIN_PASSWORD 未配置：smoke_check 拒绝用内置默认口令创建 superuser")
        created = User.objects.create_superuser(
            username=username, email="smoke_admin@example.com", password=smoke_password
        )
        return created, True

    def _cleanup_smoke_superuser(self, user: Any) -> None:
        """删除本次冒烟新建的 smoke_admin，避免超级用户残留真实库（安全审计 C-03）。"""
        User = get_user_model()
        User.objects.filter(pk=user.pk, username="smoke_admin").delete()

    def _check_admin_pages(self, client: Client) -> None:
        paths: list[Any] = ["/admin/", "/admin/cases/case/", "/admin/contracts/contract/"]
        for p in paths:
            resp = client.get(p, follow=True, HTTP_HOST="localhost")
            if resp.status_code != 200:
                raise CommandError(f"Admin 冒烟失败:GET {p} -> {resp.status_code}")

    def _check_upload_endpoints(self, client: Client) -> None:
        def _build_smoke_upload(filename: str) -> SimpleUploadedFile:
            return SimpleUploadedFile(filename, b"smoke", content_type="text/plain")

        with patch("apps.core.dependencies.build_auto_namer_service", return_value=_DummyAutoNamerService()):
            resp = client.post(
                "/api/v1/automation/auto-namer/process",
                data={"file": _build_smoke_upload("smoke-auto-namer.txt")},
                HTTP_HOST="localhost",
            )
        if resp.status_code != 200:
            raise CommandError(f"上传冒烟失败:auto-namer/process: {resp.status_code}")
        payload = resp.json()
        if payload.get("text") != "ok" or payload.get("error") is not None:
            raise CommandError(f"上传冒烟失败:auto-namer 返回异常 {json.dumps(payload, ensure_ascii=False)}")
        with (
            patch(
                "apps.core.dependencies.build_document_processing_service",
                return_value=_DummyDocumentProcessorService(),
            ),
            patch(
                "apps.core.dependencies.automation_adapters.build_document_processing_service",
                return_value=_DummyDocumentProcessorService(),
            ),
        ):
            resp2 = client.post(
                "/api/v1/automation/file/upload",
                data={"file": _build_smoke_upload("smoke-file-upload.txt")},
                HTTP_HOST="localhost",
            )
        if resp2.status_code != 200:
            raise CommandError(f"上传冒烟失败:file/upload: {resp2.status_code}")
        payload2 = resp2.json()
        if payload2.get("success") is not True:
            raise CommandError(f"上传冒烟失败:file/upload 返回异常 {json.dumps(payload2, ensure_ascii=False)}")

    def _check_websocket(self, client: Client, user: Any) -> None:
        logger.info("WebSocket 冒烟检查已跳过: litigation/mock-trial websocket 已下线")

    def _check_django_q(self) -> None:
        import logging

        from django_q.models import Task

        from apps.core.tasking import submit_task

        logger = logging.getLogger(__name__)
        task_id = submit_task("apps.automation.management.commands.smoke_check.smoke_q_task", 20, 22)
        env = dict(os.environ)
        env.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
        if self._database_path:
            env["DATABASE_PATH"] = self._database_path
        env.setdefault("DJANGO_DEBUG", "1")
        proc = SubprocessRunner(allowed_programs={str(sys.executable)}).popen(
            args=[],
            cwd=str(Path(__file__).resolve().parents[4] / "apiSystem"),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            t = Task.objects.filter(id=task_id).first()
            if t:
                if t.success:
                    if str(t.result).strip() != "42":
                        raise CommandError(f"django-q 冒烟失败:结果不正确(期望 42,得到 {t.result!r})")
                    proc.wait(timeout=10)
                    return
                if t.stopped and (not t.success):
                    proc.wait(timeout=10)
                    raise CommandError(f"django-q 冒烟失败:任务执行失败(result={t.result!r})")
            if proc.poll() is not None and (not t):
                break
            time.sleep(0.3)
        try:
            proc.wait(timeout=5)
        except Exception:
            logger.exception("操作失败")
            proc.kill()
        raise CommandError("django-q 冒烟失败:任务未在超时时间内完成")

    def _check_deployment_capabilities(self) -> None:
        """报告这台部署到底能用哪些能力（云端取字 / 分歧裁定），不能用的说清该改哪一项。

        判据：**缺 key / 没开开关是配置选择，不是冒烟未通过**——所以本检查只 WARNING、
        永不 raise、永不影响退出码（与 :meth:`_check_disk_space` 的 warning 分支同口径；
        那一处只有 critical 才抛，这里是「本来就可能没配」的东西，连 critical 都没有）。
        让 ``smoke_check`` 的退出码去反映「这台机器没配 DeepSeek」，结果是所有人都得加
        ``--skip-*`` 才能绿，真出问题时反而没人看输出。

        整段可以用 ``--skip-capabilities`` 跳过（只要连通性、不关心能力清单时用）。
        """
        from apps.pdf_splitting.services.capabilities import deployment_capabilities

        capabilities = deployment_capabilities()
        notes: list[str] = capabilities.get("notes") or []
        if not notes:
            self.stdout.write(self.style.SUCCESS("✅ 部署能力：云端取字 / 分歧裁定均可用"))
            return
        for note in notes:
            self.stdout.write(self.style.WARNING(f"⚠️ {note}"))

    def _check_disk_space(self, warning_pct: float, critical_pct: float) -> None:
        from apps.core.tasking.cleanup_tasks import check_disk_space

        result = check_disk_space(warning_pct=warning_pct, critical_pct=critical_pct)
        status = result.get("status", "error")
        if status == "critical":
            raise CommandError(
                f"磁盘空间严重不足: {result.get('used_pct')}% >= {critical_pct}% "
                f"(可用 {result.get('available_gb', '?')}GB / 总计 {result.get('total_gb', '?')}GB)"
            )
        if status == "warning":
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  磁盘空间警告: {result.get('used_pct')}% >= {warning_pct}% "
                    f"(可用 {result.get('available_gb', '?')}GB / 总计 {result.get('total_gb', '?')}GB)"
                )
            )
        else:
            self.stdout.write(
                f"💾 磁盘空间: {result.get('used_pct')}% "
                f"(可用 {result.get('available_gb', '?')}GB / 总计 {result.get('total_gb', '?')}GB)"
            )
