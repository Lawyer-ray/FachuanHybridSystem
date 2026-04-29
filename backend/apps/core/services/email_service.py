"""
邮件发送服务

提供密码重置邮件和通知邮件的发送功能。
"""

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .email_config_service import EmailConfigService

logger = logging.getLogger(__name__)


class EmailService:
    """邮件发送服务"""

    @classmethod
    def _configure_email_backend(cls) -> None:
        """动态配置邮件后端"""
        config = EmailConfigService.get_config()

        settings.EMAIL_HOST = config["EMAIL_HOST"]
        settings.EMAIL_PORT = config["EMAIL_PORT"]
        settings.EMAIL_USE_SSL = config["EMAIL_USE_SSL"]
        settings.EMAIL_USE_TLS = config["EMAIL_USE_TLS"]
        settings.EMAIL_HOST_USER = config["EMAIL_HOST_USER"]
        settings.EMAIL_HOST_PASSWORD = config["EMAIL_HOST_PASSWORD"]

    @classmethod
    def send_password_reset_email(
        cls,
        to_email: str,
        username: str,
        reset_url: str,
        expires_minutes: int = 30,
    ) -> bool:
        """
        发送密码重置邮件

        Args:
            to_email: 收件人邮箱
            username: 用户名
            reset_url: 重置链接
            expires_minutes: 链接有效期（分钟）

        Returns:
            是否发送成功
        """
        if not EmailConfigService.is_configured():
            logger.error("邮件服务未配置，请在系统配置中设置 SMTP 信息")
            return False

        try:
            cls._configure_email_backend()
            config = EmailConfigService.get_config()

            subject = f"{config['EMAIL_SUBJECT_PREFIX']} 密码重置"

            # 使用模板渲染 HTML 邮件
            html_message = render_to_string(
                "emails/password_reset.html",
                {
                    "username": username,
                    "reset_url": reset_url,
                    "expires_minutes": expires_minutes,
                    "site_name": config["EMAIL_FROM_NAME"],
                },
            )

            plain_message = strip_tags(html_message)

            from_email = f"{config['EMAIL_FROM_NAME']} <{config['EMAIL_HOST_USER']}>"

            send_mail(
                subject=subject,
                message=plain_message,
                from_email=from_email,
                recipient_list=[to_email],
                html_message=html_message,
                fail_silently=False,
            )

            logger.info(f"密码重置邮件已发送至 {to_email[:3]}***{to_email[-4:]}")
            return True

        except (ConnectionError, OSError, RuntimeError) as e:
            logger.error(f"发送邮件失败: {e}", exc_info=True)
            return False

    @classmethod
    def send_password_changed_notification(
        cls,
        to_email: str,
        username: str,
    ) -> bool:
        """
        发送密码修改通知

        Args:
            to_email: 收件人邮箱
            username: 用户名

        Returns:
            是否发送成功
        """
        if not EmailConfigService.is_configured():
            return False

        try:
            cls._configure_email_backend()
            config = EmailConfigService.get_config()

            subject = f"{config['EMAIL_SUBJECT_PREFIX']} 密码已修改"

            html_message = render_to_string(
                "emails/password_changed.html",
                {
                    "username": username,
                    "site_name": config["EMAIL_FROM_NAME"],
                },
            )

            plain_message = strip_tags(html_message)

            from_email = f"{config['EMAIL_FROM_NAME']} <{config['EMAIL_HOST_USER']}>"

            send_mail(
                subject=subject,
                message=plain_message,
                from_email=from_email,
                recipient_list=[to_email],
                html_message=html_message,
                fail_silently=False,
            )

            logger.info(f"密码修改通知已发送至 {to_email[:3]}***{to_email[-4:]}")
            return True

        except (ConnectionError, OSError, RuntimeError) as e:
            logger.error(f"发送通知邮件失败: {e}", exc_info=True)
            return False
