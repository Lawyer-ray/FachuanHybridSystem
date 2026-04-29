"""
密码重置服务

提供密码重置的核心业务逻辑。
"""

import logging

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.core.services.email_service import EmailService
from apps.organization.models import Lawyer

logger = logging.getLogger(__name__)


class PasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """自定义密码重置 Token 生成器"""

    def _make_hash_value(self, user: Lawyer, timestamp: int) -> str:
        # 包含用户密码哈希、时间戳、最后登录时间
        # 密码修改后 token 自动失效
        login_timestamp = (
            ""
            if user.last_login is None
            else user.last_login.replace(microsecond=0, tzinfo=None)
        )
        return f"{user.pk}{user.password}{timestamp}{login_timestamp}"


password_reset_token_generator = PasswordResetTokenGenerator()


class PasswordResetService:
    """密码重置服务"""

    # Token 有效期（分钟）
    TOKEN_EXPIRY_MINUTES = 30

    # 发送频率限制（秒）
    SEND_COOLDOWN_SECONDS = 60

    @classmethod
    def request_password_reset(cls, email: str) -> tuple[bool, str]:
        """
        请求密码重置

        Args:
            email: 用户邮箱

        Returns:
            (是否成功, 消息)
        """
        try:
            user = Lawyer.objects.filter(email=email, is_active=True).first()

            # 即使用户不存在也返回成功（防止用户枚举）
            if not user:
                logger.warning(f"尝试重置不存在的邮箱: {email[:3]}***{email[-4:]}")
                return True, "如果该邮箱存在，我们已发送重置链接"

            # 检查发送频率
            if cls._is_rate_limited(user):
                return False, "请稍后再试，一分钟内只能请求一次"

            # 生成 token
            token = password_reset_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            # 构建重置链接（前端页面地址）
            reset_url = f"/reset-password?uid={uid}&token={token}"

            # 发送邮件
            success = EmailService.send_password_reset_email(
                to_email=email,
                username=user.username or user.phone or "用户",
                reset_url=reset_url,
                expires_minutes=cls.TOKEN_EXPIRY_MINUTES,
            )

            if success:
                # 记录最后发送时间
                cls._update_last_send_time(user)
                logger.info(f"密码重置邮件已发送: user_id={user.pk}")
                return True, "重置链接已发送到您的邮箱"
            else:
                return False, "邮件发送失败，请稍后再试或联系管理员"

        except (ValueError, TypeError, Lawyer.DoesNotExist) as e:
            logger.error(f"请求密码重置失败: {e}", exc_info=True)
            return False, "系统错误，请稍后再试"

    @classmethod
    def verify_reset_token(cls, uid: str, token: str) -> tuple[bool, Lawyer | None, str]:
        """
        验证重置 token

        Args:
            uid: 用户 ID（base64 编码）
            token: 重置 token

        Returns:
            (是否有效, 用户对象, 消息)
        """
        try:
            # 解码用户 ID
            user_id = force_str(urlsafe_base64_decode(uid))
            user = Lawyer.objects.filter(pk=user_id, is_active=True).first()

            if not user:
                return False, None, "无效的重置链接"

            # 验证 token
            if not password_reset_token_generator.check_token(user, token):
                return False, None, "重置链接已过期或无效"

            return True, user, "Token 有效"

        except (ValueError, TypeError, UnicodeDecodeError, Lawyer.DoesNotExist) as e:
            logger.error(f"验证 token 失败: {e}", exc_info=True)
            return False, None, "无效的重置链接"

    @classmethod
    def reset_password(cls, uid: str, token: str, new_password: str) -> tuple[bool, str]:
        """
        重置密码

        Args:
            uid: 用户 ID（base64 编码）
            token: 重置 token
            new_password: 新密码

        Returns:
            (是否成功, 消息)
        """
        try:
            # 先验证 token
            is_valid, user, message = cls.verify_reset_token(uid, token)

            if not is_valid or user is None:
                return False, message

            # 设置新密码
            user.set_password(new_password)
            user.save(update_fields=["password"])

            # 发送密码修改通知
            if user.email:
                EmailService.send_password_changed_notification(
                    to_email=user.email,
                    username=user.username or user.phone or "用户",
                )

            logger.info(f"用户 {user.pk} 密码重置成功")
            return True, "密码重置成功"

        except (ValueError, TypeError) as e:
            logger.error(f"重置密码失败: {e}", exc_info=True)
            return False, "系统错误，请稍后再试"

    @classmethod
    def _is_rate_limited(cls, user: Lawyer) -> bool:
        """检查是否被限流"""
        cache_key = f"password_reset_last_send_{user.pk}"
        last_send = cache.get(cache_key)

        if last_send:
            elapsed = (timezone.now() - last_send).total_seconds()
            if elapsed < cls.SEND_COOLDOWN_SECONDS:
                return True

        return False

    @classmethod
    def _update_last_send_time(cls, user: Lawyer) -> None:
        """更新最后发送时间"""
        cache_key = f"password_reset_last_send_{user.pk}"
        cache.set(cache_key, timezone.now(), cls.SEND_COOLDOWN_SECONDS)
