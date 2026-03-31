"""Django management command."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from typing import Any
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.test import Client

from apps.core.utils.path import Path
from apps.core.infrastructure.subprocess_runner import SubprocessRunner

logger = logging.getLogger(__name__)


def smoke_q_task(a: int, b: int) -> int:
    return a + b


class _DummyAutoNamerService:
    def process_document_for_naming(
        self, uploaded_file: Any, prompt: Any, model: Any, limit: Any | None = None, preview_page: Any | None = None
    ) -> None:
        return {"text": "ok", "ollama_response": {"filename": uploaded_file.name}, "error": None}  # type: ignore[return-value]


class _DummyDocumentProcessorService:
    class _Result:
        def __init__(self, file_name: str) -> None:
            self.success = True
            self.file_info = {"name": file_name}
            self.extraction = {"text": "ok"}
            self.processing_params = {}  # type: ignore[var-annotated]
            self.error = None

    def process_uploaded_file(
        self, uploaded_file: Any, limit: Any | None = None, preview_page: Any | None = None
    ) -> None:
        return self._Result(getattr(uploaded_file, "name", "unknown"))  # type: ignore[return-value]


class Command(BaseCommand):
    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--database-path", default=None)
        parser.add_argument("--skip-migrate", action="store_true", default=False)
        parser.add_argument("--skip-admin", action="store_true", default=False)
        parser.add_argument("--skip-upload", action="store_true", default=False)
        parser.add_argument("--skip-websocket", action="store_true", default=False)
        parser.add_argument("--skip-q", action="store_true", default=False)

    def handle(self, *args, **options: Any) -> None:  # type: ignore[no-untyped-def]
        self._database_path = None
        self._maybe_switch_sqlite_db(options.get("database_path"))
        if not options.get("skip_migrate"):
            call_command("migrate", "--noinput", verbosity=0)
        user = self._ensure_smoke_superuser()
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
        self.stdout.write(self.style.SUCCESS("✅ smoke_check 通过"))

    def _maybe_switch_sqlite_db(self, database_path: str | None) -> None:
        if not database_path:
            return
        default_db = settings.DATABASES.get("default", {})
        if default_db.get("ENGINE") != "django.db.backends.sqlite3":
            raise CommandError("--database-path 仅支持 sqlite3(当前不是 sqlite)")
        db_path = Path(database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = str(db_path)  # type: ignore[assignment]
        settings.DATABASES["default"]["NAME"] = str(db_path)
        for conn in connections.all():
            conn.close()

    def _ensure_smoke_superuser(self) -> Any:
        User = get_user_model()
        username = "smoke_admin"
        user = User.objects.filter(username=username).first()
        if user:
            if not bool(getattr(user, "is_staff", False)):
                user.is_staff = True
                user.save(update_fields=["is_staff"])
            return user
        smoke_password = getattr(settings, "SMOKE_ADMIN_PASSWORD", "smoke_admin_password")
        return User.objects.create_superuser(  # type: ignore[attr-defined]
            username=username, email="smoke_admin@example.com", password=smoke_password
        )

    def _check_admin_pages(self, client: Client) -> None:
        paths: list[Any] = ["/admin/", "/admin/cases/case/", "/admin/contracts/contract/"]
        for p in paths:
            resp = client.get(p, HTTP_HOST="localhost")
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
        from django_q.tasks import async_task

        logger = logging.getLogger(__name__)
        task_id = async_task("apps.automation.management.commands.smoke_check.smoke_q_task", 20, 22)
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
