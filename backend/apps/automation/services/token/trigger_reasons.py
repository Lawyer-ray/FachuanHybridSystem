"""Business logic services."""

from __future__ import annotations


class TokenTriggerReason:
    TOKEN_EXPIRED = "token_expired"
    NO_TOKEN = "no_token"
    MANUAL_TRIGGER = "manual_trigger"
    AUTO_REFRESH = "auto_refresh"
    SYSTEM_STARTUP = "system_startup"
    TOKEN_NEEDED = "token_needed"
    MANUAL_LOGIN_TEST = "manual_login_test"


TOKEN_TRIGGER_REASON_DISPLAY = {
    TokenTriggerReason.TOKEN_EXPIRED: "🕐 Token过期",
    TokenTriggerReason.NO_TOKEN: "🚫 无Token",
    TokenTriggerReason.MANUAL_TRIGGER: "👤 手动触发",
    TokenTriggerReason.AUTO_REFRESH: "🔄 自动刷新",
    TokenTriggerReason.SYSTEM_STARTUP: "🚀 系统启动",
    TokenTriggerReason.TOKEN_NEEDED: "🧩 业务需要Token",
    TokenTriggerReason.MANUAL_LOGIN_TEST: "🧪 手动登录测试",
}
