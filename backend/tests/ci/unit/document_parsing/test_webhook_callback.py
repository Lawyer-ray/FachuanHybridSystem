"""云端回调（webhook）链路测试：鉴权、幂等、未配置时回退轮询。

覆盖三件事：
1. 签名错误 / 缺签名 → 拒绝且不写库；
2. 重复推送 → 幂等（已终态不被改写、不被重复处理）；
3. 未配置回调 → 端点视为不存在，后端走原有轮询（不带 callback）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.document_parsing.api.webhook_api import receive_webhook
from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.services.callback_config import is_callback_enabled, webhook_url, webhook_url_for_record
from apps.document_parsing.services.callback_dispatch_service import (
    ACCEPTED,
    DUPLICATE,
    REJECTED_SIGNATURE,
    REJECTED_TASK_NOT_FOUND,
    DocumentParsingCallbackDispatchService,
)
from apps.document_parsing.services.callback_seed import callback_uid, record_id_from_uid
from apps.document_parsing.services.webhook_signature import mineru_checksum, textin_signature
from apps.document_parsing.tasks import _callback_kwargs

_UID = "mineru-account-uid"
_SECRET = "textin-callback-secret"  # pragma: allowlist secret


def _record(**overrides: Any) -> DocumentParsingTask:
    defaults: dict[str, Any] = {
        "file_name": "doc.pdf",
        "file_path": "/tmp/doc.pdf",
        "file_size": 10,
        "status": DocumentParsingTask.Status.PROCESSING,
    }
    defaults.update(overrides)
    return DocumentParsingTask.objects.create(**defaults)


def _mineru_body(*, uid: str, seed: str, state: str = "done", checksum: str | None = None) -> bytes:
    """构造 MinerU 回调体：content 是 JSON 字符串，checksum 覆盖其原文。

    注意 checksum 里的 uid 是**回调时带回来的那个 uid**（``dp-{id}-{后缀}``），
    不是配置项里的账号 uid——后者是服务端的“私钥”，不随请求传输。
    """
    content = json.dumps(
        {"data": {"extract_result": [{"state": state, "full_zip_url": "https://example.com/r.zip"}]}},
        ensure_ascii=False,
    )
    body = {
        "seed": seed,
        "checksum": checksum if checksum is not None else mineru_checksum(uid, seed, content),
        "content": content,
    }
    return json.dumps(body, ensure_ascii=False).encode()


@pytest.fixture
def callback_settings(settings: Any) -> Any:
    settings.DOCUMENT_PARSE_WEBHOOK_BASE_URL = "https://api.example.com"
    settings.MINERU_CALLBACK_UID = _UID
    settings.TEXTIN_CALLBACK_SECRET = _SECRET
    return settings


class TestSignatureVerification:
    """签名错误必须拒绝，且不能碰任务记录。"""

    @pytest.mark.django_db
    def test_mineru_wrong_checksum_rejected(self, callback_settings: Any) -> None:
        record = _record(callback_seed="seed-1")
        uid = callback_uid(record.id)
        body = _mineru_body(uid=uid, seed="seed-1", checksum="0" * 64)
        headers = {"x-callback-url": f"https://api.example.com/hook?uid={uid}"}

        outcome = DocumentParsingCallbackDispatchService().handle("mineru", body, headers)

        assert outcome == REJECTED_SIGNATURE
        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.PROCESSING

    @pytest.mark.django_db
    def test_mineru_seed_mismatch_with_record_rejected(self, callback_settings: Any) -> None:
        """checksum 自洽但 seed 不是这条记录发出去的 → 定位失败（重放防护）。"""
        record = _record(callback_seed="real-seed")  # pragma: allowlist secret
        uid = callback_uid(record.id)
        body = _mineru_body(uid=uid, seed="other-seed")
        headers = {"x-callback-url": f"https://api.example.com/hook?uid={uid}"}

        outcome = DocumentParsingCallbackDispatchService().handle("mineru", body, headers)

        assert outcome == REJECTED_TASK_NOT_FOUND

    @pytest.mark.django_db
    def test_textin_missing_signature_rejected(self, callback_settings: Any) -> None:
        record = _record(metadata={"callback_job_id": "job-1"})
        body = json.dumps({"status": "completed", "job_id": "job-1"}).encode()

        outcome = DocumentParsingCallbackDispatchService().handle("textin", body, {})

        assert outcome == REJECTED_SIGNATURE
        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.PROCESSING

    def test_textin_signature_is_raw_body_based(self, callback_settings: Any) -> None:
        """签名对象必须是原始字节：重新序列化的 JSON 可能算出不同摘要。"""
        from apps.document_parsing.services.webhook_signature import verify_textin_signature

        raw = b'{"status": "completed",  "job_id": "j1"}'  # 注意多余空格
        good = textin_signature(_SECRET, raw)

        assert verify_textin_signature(secret=_SECRET, raw_body=raw, signature=good) is True
        assert (
            verify_textin_signature(secret=_SECRET, raw_body=json.dumps(json.loads(raw)).encode(), signature=good)
            is False
        )
        assert verify_textin_signature(secret="", raw_body=raw, signature=good) is False


class TestIdempotency:
    """重复推送不能重复处理。"""

    @pytest.mark.django_db
    def test_duplicate_push_does_not_rewrite_completed_record(self, callback_settings: Any) -> None:
        record = _record(
            callback_seed="seed-2",
            status=DocumentParsingTask.Status.COMPLETED,
            text="原始结果",
            backend_used="mineru",
        )
        uid = callback_uid(record.id)
        headers = {"x-callback-url": f"https://api.example.com/hook?uid={uid}"}

        first = DocumentParsingCallbackDispatchService().handle(
            "mineru", _mineru_body(uid=uid, seed="seed-2", state="done"), headers
        )
        second = DocumentParsingCallbackDispatchService().handle(
            "mineru", _mineru_body(uid=uid, seed="seed-2", state="done"), headers
        )

        assert first == DUPLICATE
        assert second == DUPLICATE
        record.refresh_from_db()
        assert record.text == "原始结果"
        assert record.status == DocumentParsingTask.Status.COMPLETED

    @pytest.mark.django_db
    def test_duplicate_push_does_not_downgrade_failed_to_completed(self, callback_settings: Any) -> None:
        record = _record(callback_seed="seed-3", status=DocumentParsingTask.Status.FAILED, error_message="先前的失败")
        uid = callback_uid(record.id)
        headers = {"x-callback-url": f"https://api.example.com/hook?uid={uid}"}

        outcome = DocumentParsingCallbackDispatchService().handle(
            "mineru", _mineru_body(uid=uid, seed="seed-3", state="done"), headers
        )

        assert outcome == DUPLICATE
        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.FAILED
        assert record.error_message == "先前的失败"

    @pytest.mark.django_db
    def test_first_successful_push_writes_result(self, callback_settings: Any) -> None:
        record = _record(callback_seed="seed-4")
        uid = callback_uid(record.id)
        headers = {"x-callback-url": f"https://api.example.com/hook?uid={uid}"}

        with patch.object(
            DocumentParsingCallbackDispatchService,
            "_build_mineru_result",
            return_value={
                "success": True,
                "text": "全文",
                "markdown": "# md",
                "metadata": {},
                "parse_method": "mineru",
            },
        ):
            outcome = DocumentParsingCallbackDispatchService().handle(
                "mineru", _mineru_body(uid=uid, seed="seed-4", state="done"), headers
            )

        assert outcome == ACCEPTED
        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.COMPLETED
        assert record.text == "全文"
        assert record.backend_used == "mineru"

    @pytest.mark.django_db
    def test_mineru_failed_state_marks_failed(self, callback_settings: Any) -> None:
        record = _record(callback_seed="seed-5")
        uid = callback_uid(record.id)
        headers = {"x-callback-url": f"https://api.example.com/hook?uid={uid}"}

        outcome = DocumentParsingCallbackDispatchService().handle(
            "mineru", _mineru_body(uid=uid, seed="seed-5", state="failed"), headers
        )

        assert outcome == ACCEPTED
        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.FAILED


class TestCallbackEndpointDisabledByConfig:
    """未配置回调 → 端点不生效（不能变成匿名可写的入口）。"""

    @pytest.mark.django_db
    def test_endpoint_returns_404_when_not_configured(self, settings: Any) -> None:
        settings.DOCUMENT_PARSE_WEBHOOK_BASE_URL = ""
        settings.MINERU_CALLBACK_UID = _UID

        class _Req:
            body = b"{}"
            headers: dict[str, str] = {}

        resp = receive_webhook(_Req(), "mineru")  # type: ignore[arg-type]

        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_endpoint_404_when_uid_missing(self, settings: Any) -> None:
        """只配基地址、缺 MinerU uid：验签材料不全，端点同样不开放。"""
        settings.DOCUMENT_PARSE_WEBHOOK_BASE_URL = "https://api.example.com"
        settings.MINERU_CALLBACK_UID = ""

        class _Req:
            body = b"{}"
            headers: dict[str, str] = {}

        assert receive_webhook(_Req(), "mineru").status_code == 404  # type: ignore[arg-type]

    def test_signature_failure_maps_to_403(self, callback_settings: Any) -> None:
        class _Req:
            body = b'{"seed": "s", "checksum": "bad", "content": "{}"}'
            headers = {"X-Callback-Url": "https://api.example.com/hook?uid=dp-1-abc"}

        assert receive_webhook(_Req(), "mineru").status_code == 403  # type: ignore[arg-type]

    def test_unknown_provider_rejected(self, callback_settings: Any) -> None:
        class _Req:
            body = b"{}"
            headers: dict[str, str] = {}

        assert receive_webhook(_Req(), "mineru2").status_code == 404  # type: ignore[arg-type]


class TestConfigGating:
    """回调启用条件与 URL 拼装。"""

    def test_disabled_without_base_url(self, settings: Any) -> None:
        settings.DOCUMENT_PARSE_WEBHOOK_BASE_URL = ""
        settings.MINERU_CALLBACK_UID = _UID
        settings.TEXTIN_CALLBACK_SECRET = _SECRET

        assert is_callback_enabled("mineru") is False
        assert webhook_url("textin") is None

    def test_mineru_requires_uid(self, settings: Any) -> None:
        settings.DOCUMENT_PARSE_WEBHOOK_BASE_URL = "https://api.example.com/"
        settings.MINERU_CALLBACK_UID = ""

        assert is_callback_enabled("mineru") is False

    def test_textin_requires_secret(self, settings: Any) -> None:
        settings.DOCUMENT_PARSE_WEBHOOK_BASE_URL = "https://api.example.com"
        settings.TEXTIN_CALLBACK_SECRET = ""

        assert is_callback_enabled("textin") is False

    def test_url_shape(self, callback_settings: Any) -> None:
        assert webhook_url("mineru") == "https://api.example.com/api/v1/document-parsing/webhook/mineru"
        with_uid = webhook_url_for_record("mineru", 42)
        assert with_uid is not None
        assert with_uid.startswith("https://api.example.com/api/v1/document-parsing/webhook/mineru?uid=dp-42-")

    def test_local_backend_never_uses_callback(self, callback_settings: Any) -> None:
        assert is_callback_enabled("local") is False

    def test_uid_roundtrip(self) -> None:
        uid = callback_uid(7)
        assert record_id_from_uid(uid) == 7
        assert record_id_from_uid("garbage") is None
        assert record_id_from_uid("dp-abc-xyz") is None


class TestFallbackToPolling:
    """未配置回调时 worker 不带 callback 参数（= 原有轮询路径）。"""

    def test_no_callback_kwargs_without_config(self, settings: Any) -> None:
        settings.DOCUMENT_PARSE_WEBHOOK_BASE_URL = ""
        settings.MINERU_CALLBACK_UID = _UID

        assert _callback_kwargs(1, "mineru", "seed") == {}

    def test_no_callback_kwargs_without_seed(self, callback_settings: Any) -> None:
        assert _callback_kwargs(1, "mineru", "") == {}

    def test_no_callback_kwargs_for_local(self, callback_settings: Any) -> None:
        assert _callback_kwargs(1, "local", "seed") == {}

    def test_callback_kwargs_present_when_enabled(self, callback_settings: Any) -> None:
        kwargs = _callback_kwargs(9, "mineru", "seed-x")

        assert kwargs["callback_seed"] == "seed-x"
        assert "/webhook/mineru?uid=dp-9-" in kwargs["callback_url"]

    def test_auto_resolves_to_concrete_platform(self, callback_settings: Any) -> None:
        with patch("apps.document_parsing.services.parser_factory.resolve_auto_backend", return_value="textin"):
            kwargs = _callback_kwargs(9, "auto", "seed-x")

        assert kwargs["callback_url"].endswith("/webhook/textin")

    def test_mineru_parse_document_without_callback_polls(self) -> None:
        """MineruBackend 未收到 callback 参数 → 上传 payload 不带 callback/seed。"""
        from apps.document_parsing.services.backends.mineru_backend import MineruBackend

        backend = MineruBackend(api_key="k")
        response = MagicMock()
        response.json.return_value = {"code": 0, "data": {"batch_id": "b1", "file_urls": ["https://up"]}}
        response.raise_for_status = MagicMock()
        client = MagicMock()
        client.post.return_value = response

        with patch("apps.document_parsing.services.backends.mineru_backend.get_sync_http_client", return_value=client):
            backend._request_upload_url("a.pdf", callback=None, seed=None)

        payload = client.post.call_args.kwargs["json"]
        assert "callback" not in payload
        assert "seed" not in payload

    def test_mineru_parse_document_with_callback_sends_params(self) -> None:
        from apps.document_parsing.services.backends.mineru_backend import MineruBackend

        backend = MineruBackend(api_key="k")
        response = MagicMock()
        response.json.return_value = {"code": 0, "data": {"batch_id": "b1", "file_urls": ["https://up"]}}
        response.raise_for_status = MagicMock()
        client = MagicMock()
        client.post.return_value = response

        with patch("apps.document_parsing.services.backends.mineru_backend.get_sync_http_client", return_value=client):
            backend._request_upload_url("a.pdf", callback="https://cb/mineru", seed="s1")

        payload = client.post.call_args.kwargs["json"]
        assert payload["callback"] == "https://cb/mineru"
        assert payload["seed"] == "s1"

    def test_textin_create_job_passes_webhook_only_when_given(self, tmp_path: Path) -> None:
        from apps.document_parsing.services.backends.textin_backend import TextinBackend

        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        backend = TextinBackend(app_id="a", secret_code="s")  # pragma: allowlist secret
        client = MagicMock()
        client.parse.create_job.return_value = MagicMock(job_id="job-1")
        backend._client = client

        backend._create_job(pdf, extract_tables=True)
        assert client.parse.create_job.call_args.kwargs["webhook"] is None

        backend._create_job(pdf, extract_tables=True, webhook="https://cb/textin")
        assert client.parse.create_job.call_args.kwargs["webhook"] == "https://cb/textin"


def _sha256_hex(text: str) -> str:
    """测试用：显式算一次摘要，确认实现与官方公式一致。"""
    return hashlib.sha256(text.encode()).hexdigest()


class TestChecksumFormula:
    def test_matches_official_concatenation(self) -> None:
        content = '{"data": {}}'
        assert mineru_checksum("uid", "seed", content) == _sha256_hex(f"uidseed{content}")
