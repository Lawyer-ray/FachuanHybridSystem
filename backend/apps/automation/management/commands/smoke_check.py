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

from apps.core.path import Path
from apps.core.subprocess_runner import SubprocessRunner

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
        user = self._ensure_smoke_superuser()  # type: ignore[func-returns-value]
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

    def _ensure_smoke_superuser(self) -> None:
        User = get_user_model()
        username = "smoke_admin"
        user = User.objects.filter(username=username).first()
        if user:
            if not user.is_staff:
                user.is_staff = True
                user.save(update_fields=["is_staff"])
            return user  # type: ignore[no-any-return]
        return User.objects.create_superuser(
            username=username, email="smoke_admin@example.com", password="smoke_admin_password"
        )  # type: ignore[no-any-return, attr-defined]

    def _check_admin_pages(self, client: Client) -> None:
        paths: list[Any] = ["/admin/", "/admin/cases/case/", "/admin/contracts/contract/"]
        for p in paths:
            resp = client.get(p, HTTP_HOST="localhost")
            if resp.status_code != 200:
                raise CommandError(f"Admin 冒烟失败:GET {p} -> {resp.status_code}")

    def _check_upload_endpoints(self, client: Client) -> None:
        file_obj = SimpleUploadedFile("hello.txt", b"hello", content_type="text/plain")
        with patch("apps.core.dependencies.build_auto_namer_service", return_value=_DummyAutoNamerService()):
            resp = client.post("/api/v1/automation/auto-namer/process", data={}, HTTP_HOST="localhost")
        if resp.status_code != 200:
            raise CommandError(f"上传冒烟失败:auto-namer/process: {resp.status_code}")
        payload = resp.json()
        if payload.get("text") != "ok" or payload.get("error") is not None:
            raise CommandError(f"上传冒烟失败:auto-namer 返回异常 {json.dumps(payload, ensure_ascii=False)}")
        file_obj2 = SimpleUploadedFile("hello2.txt", b"hello2", content_type="text/plain")
        with patch(
            "apps.core.dependencies.build_document_processing_service", return_value=_DummyDocumentProcessorService()
        ):
            resp2 = client.post("/api/v1/automation/file/upload", data={}, HTTP_HOST="localhost")
        if resp2.status_code != 200:
            raise CommandError(f"上传冒烟失败:file/upload: {resp2.status_code}")
        payload2 = resp2.json()
        if payload2.get("success") is not True:
            raise CommandError(f"上传冒烟失败:file/upload 返回异常 {json.dumps(payload2, ensure_ascii=False)}")

    def _check_websocket(self, client: Client, user: Any) -> None:
        from channels.testing import WebsocketCommunicator

        from apps.cases.models import Case
        from apps.contracts.models import Contract
        from apps.core.enums import CaseType
        from apps.litigation_ai.models.session import LitigationSession

        contract = Contract.objects.create(name="smoke contract", case_type=CaseType.CIVIL)
        case = Case.objects.create(name="smoke case", contract=contract)
        session = LitigationSession.objects.create(case=case, user=user)
        cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        cookie_value = client.cookies.get(cookie_name)
        if not cookie_value:
            raise CommandError("WebSocket 冒烟失败:未获取到登录 session cookie")
        from apiSystem.asgi import application

        async def _run() -> None:
            communicator_anon = WebsocketCommunicator(application, f"/ws/litigation/sessions/{session.session_id}/")
            connected, _ = await communicator_anon.connect()
            if connected:
                await communicator_anon.disconnect()
                raise CommandError("WebSocket 冒烟失败:匿名用户不应 connect 成功")
            cookie_header = f"{cookie_name}={cookie_value.value}".encode()
            with patch(
                "apps.litigation_ai.services.conversation_flow_service.ConversationFlowService.handle_init",
                autospec=True,
                return_value=None,
            ):
                communicator = WebsocketCommunicator(
                    application, f"/ws/litigation/sessions/{session.session_id}/", headers=[]
                )
                connected2, _ = await communicator.connect()
                if not connected2:
                    raise CommandError("WebSocket 冒烟失败:登录用户 connect 失败")
                await communicator.disconnect()

        import asyncio

        asyncio.run(_run())

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
