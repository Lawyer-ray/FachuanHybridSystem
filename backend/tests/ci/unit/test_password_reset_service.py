"""
密码重置服务单元测试
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.organization.models import Lawyer
from apps.organization.services.auth.password_reset_service import (
    PasswordResetService,
    password_reset_token_generator,
)


class PasswordResetServiceTest(TestCase):
    """密码重置服务测试"""

    # 标准测试手机号 / 标准测试密码
    _TEST_PHONE = "13800000000"  # nosec: standard test phone
    _TEST_PASSWORD = "TestOldP@ss1"  # nosec: test fixture

    def setUp(self):
        self.user = Lawyer.objects.create_user(
            username="测试律师",
            phone=self._TEST_PHONE,
            email="test@example.com",
            password=self._TEST_PASSWORD,
        )

    @patch("apps.organization.services.auth.password_reset_service.EmailService.send_password_reset_email")
    def test_request_password_reset_success(self, mock_send_email):
        """测试请求密码重置成功"""
        mock_send_email.return_value = True

        success, message = PasswordResetService.request_password_reset("test@example.com")

        self.assertTrue(success)
        self.assertIn("已发送", message)
        mock_send_email.assert_called_once()

    def test_request_password_reset_nonexistent_email(self):
        """测试不存在的邮箱（防枚举）"""
        success, message = PasswordResetService.request_password_reset("nonexistent@example.com")

        # 即使用户不存在，也返回成功
        self.assertTrue(success)

    def test_verify_valid_token(self):
        """测试验证有效 token"""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = password_reset_token_generator.make_token(self.user)

        is_valid, user, message = PasswordResetService.verify_reset_token(uid, token)

        self.assertTrue(is_valid)
        self.assertEqual(user.pk, self.user.pk)

    def test_verify_invalid_token(self):
        """测试验证无效 token"""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        is_valid, user, message = PasswordResetService.verify_reset_token(uid, "invalid-token")

        self.assertFalse(is_valid)
        self.assertIsNone(user)

    @patch("apps.organization.services.auth.password_reset_service.EmailService.send_password_changed_notification")
    def test_reset_password_success(self, mock_send_notification):
        """测试重置密码成功"""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = password_reset_token_generator.make_token(self.user)

        mock_send_notification.return_value = True

        success, message = PasswordResetService.reset_password(uid, token, "TestNewP@ss1")

        self.assertTrue(success)

        # 验证密码已更新
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("TestNewP@ss1"))

    def test_token_invalid_after_password_change(self):
        """测试密码修改后 token 失效"""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = password_reset_token_generator.make_token(self.user)

        # 先修改密码
        self.user.set_password("TestOtherP@ss1")
        self.user.save()

        # 验证旧 token 应该失效
        is_valid, _, _ = PasswordResetService.verify_reset_token(uid, token)
        self.assertFalse(is_valid)
