"""验证码、Token、登录相关日志 Mixin"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class TokenLoggingMixin:
    """验证码、Token、登录相关日志方法"""

    @staticmethod
    def log_captcha_recognition_start(image_size: int | None = None, **kwargs: Any) -> None:
        """记录验证码识别开始"""
        extra: dict[str, Any] = {
            "action": "captcha_recognition_start",
            "timestamp": datetime.now().isoformat(),
        }
        if image_size is not None:
            extra["image_size"] = image_size
        extra.update(kwargs)
        logger.info("开始验证码识别", extra=extra)

    @staticmethod
    def log_captcha_recognition_success(
        processing_time: float, result_length: int, image_size: int | None = None, **kwargs: Any
    ) -> None:
        """记录验证码识别成功"""
        extra: dict[str, Any] = {
            "action": "captcha_recognition_success",
            "success": True,
            "processing_time": processing_time,
            "result_length": result_length,
            "timestamp": datetime.now().isoformat(),
        }
        if image_size is not None:
            extra["image_size"] = image_size
        extra.update(kwargs)
        logger.info("验证码识别成功", extra=extra)

    @staticmethod
    def log_captcha_recognition_failed(
        processing_time: float, error_message: str, image_size: int | None = None, **kwargs: Any
    ) -> None:
        """记录验证码识别失败"""
        extra: dict[str, Any] = {
            "action": "captcha_recognition_failed",
            "success": False,
            "processing_time": processing_time,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
        }
        if image_size is not None:
            extra["image_size"] = image_size
        extra.update(kwargs)
        logger.error("验证码识别失败", extra=extra)

    @staticmethod
    def log_token_acquisition_start(
        acquisition_id: str, site_name: str, account: str | None = None, **kwargs: Any
    ) -> None:
        """记录Token获取开始"""
        extra: dict[str, Any] = {
            "action": "token_acquisition_start",
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "timestamp": datetime.now().isoformat(),
        }
        if account:
            extra["account"] = account
        extra.update(kwargs)
        logger.info("开始Token获取流程", extra=extra)

    @staticmethod
    def log_token_acquisition_success(
        acquisition_id: str, site_name: str, account: str, total_duration: float, **kwargs: Any
    ) -> None:
        """记录Token获取成功"""
        extra: dict[str, Any] = {
            "action": "token_acquisition_success",
            "success": True,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "total_duration": total_duration,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.info("Token获取成功", extra=extra)

    @staticmethod
    def log_token_acquisition_failed(
        acquisition_id: str,
        site_name: str,
        error_message: str,
        account: str | None = None,
        total_duration: float | None = None,
        **kwargs: Any,
    ) -> None:
        """记录Token获取失败"""
        extra: dict[str, Any] = {
            "action": "token_acquisition_failed",
            "success": False,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
        }
        if account:
            extra["account"] = account
        if total_duration is not None:
            extra["total_duration"] = total_duration
        extra.update(kwargs)
        logger.error("Token获取失败", extra=extra)

    @staticmethod
    def log_existing_token_used(
        acquisition_id: str, site_name: str, account: str, token_expires_at: str | None = None, **kwargs: Any
    ) -> None:
        """记录使用现有Token"""
        extra: dict[str, Any] = {
            "action": "existing_token_used",
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "timestamp": datetime.now().isoformat(),
        }
        if token_expires_at:
            extra["token_expires_at"] = token_expires_at
        extra.update(kwargs)
        logger.info("使用现有Token", extra=extra)

    @staticmethod
    def log_auto_login_start(acquisition_id: str, site_name: str, account: str, **kwargs: Any) -> None:
        """记录自动登录开始"""
        extra: dict[str, Any] = {
            "action": "auto_login_start",
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.info("开始自动登录", extra=extra)

    @staticmethod
    def log_auto_login_success(
        acquisition_id: str, site_name: str, account: str, login_duration: float, **kwargs: Any
    ) -> None:
        """记录自动登录成功"""
        extra: dict[str, Any] = {
            "action": "auto_login_success",
            "success": True,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "login_duration": login_duration,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.info("自动登录成功", extra=extra)

    @staticmethod
    def log_auto_login_timeout(
        acquisition_id: str,
        site_name: str,
        account: str,
        timeout_seconds: int,
        login_duration: float,
        **kwargs: Any,
    ) -> None:
        """记录自动登录超时"""
        extra: dict[str, Any] = {
            "action": "auto_login_timeout",
            "success": False,
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": account,
            "timeout_seconds": timeout_seconds,
            "login_duration": login_duration,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.error("自动登录超时", extra=extra)

    @staticmethod
    def log_login_retry(
        network_attempt: int,
        max_network_retries: int,
        captcha_attempt: int | None = None,
        max_captcha_retries: int | None = None,
        **kwargs: Any,
    ) -> None:
        """记录登录重试"""
        extra: dict[str, Any] = {
            "action": "login_retry",
            "network_attempt": network_attempt,
            "max_network_retries": max_network_retries,
            "timestamp": datetime.now().isoformat(),
        }
        if captcha_attempt is not None:
            extra["captcha_attempt"] = captcha_attempt
        if max_captcha_retries is not None:
            extra["max_captcha_retries"] = max_captcha_retries
        extra.update(kwargs)
        logger.info(f"登录重试 {network_attempt}/{max_network_retries}", extra=extra)
