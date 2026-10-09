"""安全审计第4轮：automation 域越权修复的回归测试。

覆盖：
1. document-processor /process 与 /process-by-path 收敛为管理员专用
2. court-sms 读类（detail/list）案件 ACL、公共短信全员可见
3. court-sms 写类（assign/retry/delete/batch-delete/abort/rename）管理员专用
4. captcha /recognize 匿名可访问但受 IP 级限流
5. CourtToken.token 加密落库（存密文读明文）
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.automation.api.captcha_recognition_api import _authorize_service_call, recognize_captcha
from apps.automation.api.court_sms_api import (
    abort_and_delete_sms,
    assign_case,
    batch_delete_sms,
    delete_sms,
    rename_document,
    retry_processing,
)
from apps.automation.api.document_processor_api import process_document, process_document_by_path
from apps.automation.models import CourtSMS, CourtSMSStatus, CourtToken
from apps.automation.schemas import CaptchaRecognizeIn, CourtSMSAssignCaseIn, CourtSMSBatchDeleteIn, DocumentProcessIn
from apps.automation.services.sms.court_sms_service import CourtSMSService
from apps.cases.models import CaseAssignment
from apps.core.exceptions import PermissionDenied, RateLimitError
from apps.core.exceptions.common import ForbiddenError
from apps.core.infrastructure.throttling import get_rate_limit_config
from apps.core.model_fields.encrypted import EncryptedTextField
from apps.testing.factories import CaseFactory, LawyerFactory

_factory = RequestFactory()


class _FakeSchemaEditor:
    """RunPython 回调只需要 schema_editor.connection.alias。"""

    def __init__(self, connection_obj: Any) -> None:
        self.connection = connection_obj


def _request(user: Any, method: str = "post", path: str = "/"):
    request = getattr(_factory, method)(path)
    request.user = user
    return request


def _make_case_with_assignment(lawyer: Any):
    case = CaseFactory()
    CaseAssignment.objects.create(case=case, lawyer=lawyer)
    return case


def _make_sms(case: Any = None, content: str = "【广州法院】您的文书已到达") -> CourtSMS:
    return CourtSMS.objects.create(
        content=content,
        received_at=timezone.now(),
        status=CourtSMSStatus.PENDING,
        document_file_paths=[],
        case=case,
    )


# ============================================================================
# 1. document-processor：管理员专用
# ============================================================================


class TestDocumentProcessorAdminOnly:
    @pytest.mark.django_db
    def test_process_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            process_document(request, DocumentProcessIn(file_path="documents/test.pdf", kind="pdf"))

    @pytest.mark.django_db
    def test_process_by_path_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            process_document_by_path(request, DocumentProcessIn(file_path="documents/test.pdf", kind="pdf"))

    @pytest.mark.django_db
    def test_process_by_path_admin_ok(self) -> None:
        request = _request(LawyerFactory(is_admin=True))
        with patch("apps.core.dependencies.build_document_processing_service") as mock_build:
            mock_service = MagicMock()
            mock_service.extract_document_content_by_path.return_value = {"image_url": None, "text": "hello"}
            mock_build.return_value = mock_service
            out = process_document_by_path(request, DocumentProcessIn(file_path="documents/test.pdf", kind="pdf"))
        assert out.text_excerpt == "hello"
        call_kwargs = mock_service.extract_document_content_by_path.call_args.kwargs
        # 路径必须被收敛到 MEDIA_ROOT 内
        assert call_kwargs["file_path"].endswith("documents/test.pdf")


# ============================================================================
# 2. court-sms 读类：案件 ACL
# ============================================================================


class TestCourtSmsReadAcl:
    @pytest.mark.django_db
    def test_detail_denied_for_lawyer_without_case_access(self) -> None:
        lawyer_a = LawyerFactory()
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b)
        sms = _make_sms(case=case)

        with pytest.raises(ForbiddenError):
            CourtSMSService().get_sms_detail(sms.id, user=lawyer_a)

    @pytest.mark.django_db
    def test_detail_ok_for_assigned_lawyer(self) -> None:
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b)
        sms = _make_sms(case=case)

        assert CourtSMSService().get_sms_detail(sms.id, user=lawyer_b).id == sms.id

    @pytest.mark.django_db
    def test_detail_public_sms_visible_to_all(self) -> None:
        """未绑案件的公共短信保持全员可见。"""
        lawyer_a = LawyerFactory()
        sms = _make_sms(case=None)

        assert CourtSMSService().get_sms_detail(sms.id, user=lawyer_a).id == sms.id

    @pytest.mark.django_db
    def test_detail_admin_sees_all(self) -> None:
        admin = LawyerFactory(is_admin=True)
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b)
        sms = _make_sms(case=case)

        assert CourtSMSService().get_sms_detail(sms.id, user=admin).id == sms.id

    @pytest.mark.django_db
    def test_detail_internal_call_without_user_skips_check(self) -> None:
        """worker / 管线等内部调用（不传 user）不做校验。"""
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b)
        sms = _make_sms(case=case)

        assert CourtSMSService().get_sms_detail(sms.id).id == sms.id

    @pytest.mark.django_db
    def test_list_filtered_by_case_access(self) -> None:
        lawyer_a = LawyerFactory()
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b)
        _make_sms(case=case, content="绑定B案件的短信")
        public = _make_sms(case=None, content="公共短信")

        ids_a = {s.id for s in CourtSMSService().list_sms(user=lawyer_a)}
        ids_b = {s.id for s in CourtSMSService().list_sms(user=lawyer_b)}
        ids_admin = {s.id for s in CourtSMSService().list_sms(user=LawyerFactory(is_admin=True))}
        ids_internal = {s.id for s in CourtSMSService().list_sms()}

        assert ids_a == {public.id}
        assert ids_admin == ids_internal
        assert len(ids_b) >= 2


# ============================================================================
# 3. court-sms 写类：管理员专用
# ============================================================================


class TestCourtSmsWriteAdminOnly:
    @pytest.mark.django_db
    def test_assign_case_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            asyncio.run(assign_case(request, 1, CourtSMSAssignCaseIn(case_id=1)))

    @pytest.mark.django_db
    def test_retry_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            asyncio.run(retry_processing(request, 1))

    @pytest.mark.django_db
    def test_delete_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            asyncio.run(delete_sms(request, 1))

    @pytest.mark.django_db
    def test_batch_delete_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            asyncio.run(batch_delete_sms(request, CourtSMSBatchDeleteIn(ids=[1, 2])))

    @pytest.mark.django_db
    def test_abort_and_delete_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            asyncio.run(abort_and_delete_sms(request, 1))

    @pytest.mark.django_db
    def test_rename_document_denied_for_normal_user(self) -> None:
        from apps.automation.schemas import CourtSmsDocumentRenameIn

        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            asyncio.run(rename_document(request, 1, 0, CourtSmsDocumentRenameIn(new_stem="新名字")))

    @pytest.mark.django_db
    def test_assign_case_admin_passes_gate(self) -> None:
        """管理员通过权限门并触达服务层（服务层 mock，验证门在前不在后）。"""
        request = _request(LawyerFactory(is_admin=True))
        mock_sms = MagicMock()
        mock_sms.id = 1
        mock_sms.status = "renaming"
        mock_sms.case = None
        with patch("apps.core.dependencies.automation_sms_entry.build_court_sms_service_ctx") as mock_build:
            mock_build.return_value.assign_case.return_value = mock_sms
            asyncio.run(assign_case(request, 1, CourtSMSAssignCaseIn(case_id=1)))
        mock_build.return_value.assign_case.assert_called_once()


# ============================================================================
# 4. captcha /recognize：IP 级限流
# ============================================================================


class TestCaptchaRateLimit:
    @pytest.mark.django_db
    def test_recognize_rate_limited_after_bucket_exhausted(self) -> None:
        limit, _window = get_rate_limit_config("UPLOAD", fallback_requests=20, fallback_window=60)
        # 限流 key 是 ip:<客户端IP>（rate_limit_by_user，不含 path），混跑隔离必须用独立 IP
        request = _request(None, path=f"/api/v1/automation/captcha/recognize/{uuid4().hex}")
        request.META["REMOTE_ADDR"] = f"10.77.{secrets.randbelow(254) + 1}.{secrets.randbelow(254) + 1}"
        # M-5 之后端点要求服务间共享密钥，本用例测的是限流，先过授权门
        request.META["HTTP_X_CAPTCHA_SECRET"] = "round4-test-value"  # pragma: allowlist secret

        with override_settings(CAPTCHA_RECOGNIZE_SECRET="round4-test-value"):  # pragma: allowlist secret
            with patch("apps.core.dependencies.build_captcha_service") as mock_build:
                mock_service = MagicMock()
                mock_service.recognize_from_base64.return_value = MagicMock(
                    success=True, text="AB12", processing_time=0.01, error=None
                )
                mock_build.return_value = mock_service

                for _ in range(limit):
                    out = recognize_captcha(request, CaptchaRecognizeIn(image_base64="iVBORw0KGgo="))
                    assert out.success is True

                # 第 limit+1 次触发限流（RateLimitError → 全局处理器转 429）
                with pytest.raises(RateLimitError):
                    recognize_captcha(request, CaptchaRecognizeIn(image_base64="iVBORw0KGgo="))


# ============================================================================
# 5. CourtToken：加密落库
# ============================================================================


def _raw_token_value(token_id: int) -> str | None:
    """绕过模型层解密，直读库内真实存储值（values_list 也会走 from_db_value）。"""
    from django.db import connection

    table = CourtToken._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT token FROM {table} WHERE id = %s", [token_id])
        row = cursor.fetchone()
    return str(row[0]) if row else None


class TestCourtTokenEncryption:
    @pytest.mark.django_db
    def test_encrypt_at_rest_decrypt_on_read(self) -> None:
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="acct-1",
            token="plain-jwt-secret-value",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        raw = _raw_token_value(token.id)
        assert raw is not None
        assert raw != "plain-jwt-secret-value"
        assert raw.startswith("enc:v1:")
        # 模型属性读取自动解密为明文
        assert CourtToken.objects.get(id=token.id).token == "plain-jwt-secret-value"

    @pytest.mark.django_db
    def test_update_re_encrypts_new_value(self) -> None:
        token = CourtToken.objects.create(
            site_name="court_baoquan",
            account="acct-2",
            token="first-token",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        CourtToken.objects.filter(id=token.id).update(token="second-token")
        raw = _raw_token_value(token.id)
        assert raw is not None and raw.startswith("enc:v1:")
        assert CourtToken.objects.get(id=token.id).token == "second-token"

    @pytest.mark.django_db
    def test_migration_helper_encrypts_plaintext_idempotently(self) -> None:
        """0027 迁移的 RunPython：明文行被加密、已加密行保持不变。"""
        import importlib

        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        migration = importlib.import_module("apps.automation.migrations.0027_alter_courttoken_token")
        loader = MigrationLoader(None, replace_migrations=False)
        state_apps = loader.project_state(("automation", "0027_alter_courttoken_token")).apps

        plain = CourtToken.objects.create(
            site_name="court_zxfw",
            account="acct-plain",
            token="legacy-plain",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        # 伪造一行已加密数据（模型写入会自动加密，故用裸 SQL 注入既有密文）
        field = EncryptedTextField()
        cipher = field.get_prep_value("already-enc")
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {CourtToken._meta.db_table} "
                "(site_name, account, token, token_type, expires_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ["court_zxfw", "acct-enc", cipher, "Bearer", timezone.now(), timezone.now(), timezone.now()],
            )
        enc_id_row = CourtToken.objects.values_list("id").get(account="acct-enc")
        enc_id = enc_id_row[0] if isinstance(enc_id_row, tuple) else enc_id_row

        migration.encrypt_existing_tokens(state_apps, _FakeSchemaEditor(connection))

        plain_raw = _raw_token_value(plain.id)
        assert plain_raw is not None and plain_raw != "legacy-plain" and plain_raw.startswith("enc:v1:")
        # 已加密行不被二次加密（密文保持原样）
        assert _raw_token_value(enc_id) == cipher
        # 加密后仍可解密读出
        assert CourtToken.objects.get(id=plain.id).token == "legacy-plain"

    def test_legacy_plaintext_still_readable(self) -> None:
        """存量明文行兼容：无 enc 前缀的值原样读出（迁移后逐步加密）。"""
        from apps.core.model_fields.encrypted import EncryptedTextField

        field = EncryptedTextField()
        assert field.to_python("legacy-plain-token") == "legacy-plain-token"

    def test_mask_secret_importable(self) -> None:
        """确认 scrub 工具仍可用（TokenAcquisitionHistory 脱敏钩子回归锚点）。"""
        from apps.core.security.scrub import mask_secret

        assert mask_secret("abcdefghij")  # 非空返回值即可，脱敏细节由 scrub 自身测试覆盖


# ============================================================================
# 4b. captcha /recognize：服务间共享密钥（M-5）
# ============================================================================


class TestCaptchaSecretAuth:
    """匿名 OCR 滥用防护：端点要求 X-Captcha-Secret 匹配 CAPTCHA_RECOGNIZE_SECRET。"""

    def _req(self, secret: str | None = None) -> Any:
        request = _request(None, path="/api/v1/automation/captcha/recognize")
        request.META["REMOTE_ADDR"] = f"10.88.{secrets.randbelow(254) + 1}.{secrets.randbelow(254) + 1}"
        if secret is not None:
            request.META["HTTP_X_CAPTCHA_SECRET"] = secret
        return request

    @pytest.mark.django_db
    @override_settings(CAPTCHA_RECOGNIZE_SECRET="round4-test-value")  # pragma: allowlist secret
    def test_missing_secret_403(self) -> None:
        with pytest.raises(PermissionDenied) as exc:
            _authorize_service_call(self._req())
        assert exc.value.code == "CAPTCHA_SECRET_INVALID"

    @pytest.mark.django_db
    @override_settings(CAPTCHA_RECOGNIZE_SECRET="round4-test-value")  # pragma: allowlist secret
    def test_wrong_secret_403(self) -> None:
        with pytest.raises(PermissionDenied) as exc:
            _authorize_service_call(self._req("nope"))
        assert exc.value.code == "CAPTCHA_SECRET_INVALID"

    @pytest.mark.django_db
    @override_settings(CAPTCHA_RECOGNIZE_SECRET="round4-test-value")  # pragma: allowlist secret
    def test_correct_secret_passes(self) -> None:
        """正确密钥必须静默放行（不抛异常即通过，此处显式固化该契约）。"""
        assert _authorize_service_call(self._req("round4-test-value")) is None

    @pytest.mark.django_db
    @override_settings(CAPTCHA_RECOGNIZE_SECRET="")
    def test_unconfigured_secret_fails_closed(self) -> None:
        """fail-closed：未配置密钥时连正确样式的请求也拒（端点整体不可用）。"""
        with pytest.raises(PermissionDenied) as exc:
            _authorize_service_call(self._req("round4-test-value"))
        assert exc.value.code == "CAPTCHA_SERVICE_DISABLED"

    @pytest.mark.django_db
    @override_settings(CAPTCHA_RECOGNIZE_SECRET="round4-test-value")  # pragma: allowlist secret
    def test_blank_header_403(self) -> None:
        """空字符串头不等于密钥。"""
        with pytest.raises(PermissionDenied):
            _authorize_service_call(self._req(""))
