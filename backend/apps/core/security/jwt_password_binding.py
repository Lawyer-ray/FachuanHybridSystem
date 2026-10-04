"""JWT 密码绑定（pwd_ver claim）— 改密后旧 refresh token 失效的最小实现。

安全审计 C-14 / E-07（改密不失效 token）：项目无 token 黑名单基建、Lawyer 模型
无 token 版本字段。本模块利用一个既有事实实现零迁移的等价校验：
``set_password`` 每次都会生成新的随机盐密码哈希，因此当前密码哈希本身就是
天然单调变化的「token 版本」。

机制：
- 签发：refresh token 注入 ``pwd_ver = sha256(user.password)[:16]``；
  ``refresh.access_token`` 会自动继承该 claim。
- 刷新：/token/refresh 解码后校验 claim 与用户当前密码哈希指纹一致，
  不一致（密码已改）或缺失（部署前的存量 token）即拒绝，强制重新登录。
- 访问：access token 保持无状态（最长 2h），密码更改后的暴露窗口收敛到
  access 生命周期内，等价于黑名单方案的实际防护效果。

使用方：
- ``SIMPLE_JWT`` 配置指向本模块 schema（覆盖 /token/pair 与 /token/refresh）
- ``apps.social_auth.services.token_exchange_service``（扫码登录直接铸造 token）
"""

from __future__ import annotations

import hashlib
from typing import Any, cast

from django.contrib.auth import get_user_model
from ninja_jwt import exceptions, tokens
from ninja_jwt.schema import (
    SchemaInputService,
    TokenObtainPairInputSchema,
    TokenRefreshInputSchema,
    TokenRefreshOutputSchema,
)
from ninja_jwt.settings import api_settings
from ninja_jwt.utils import token_error
from pydantic import model_validator

PWD_VER_CLAIM = "pwd_ver"

UserModel = get_user_model()


def password_fingerprint(user: Any) -> str:
    """用户当前密码哈希的短指纹（16 hex）。set_password 后必然变化。"""
    return hashlib.sha256(str(user.password).encode()).hexdigest()[:16]


def bind_password_claim(refresh: tokens.RefreshToken, user: Any) -> tokens.RefreshToken:
    """为 refresh token 注入密码指纹 claim（access token 自动继承）。"""
    refresh[PWD_VER_CLAIM] = password_fingerprint(user)
    return refresh


def verify_password_claim(refresh: tokens.RefreshToken) -> None:
    """校验 refresh token 的密码指纹与用户当前密码一致。

    Raises:
        exceptions.InvalidToken: token 缺少用户标识。
        exceptions.AuthenticationFailed: 用户不存在、claim 缺失或密码已变更。
    """
    user_id = refresh.get(api_settings.USER_ID_CLAIM)
    if user_id is None:
        raise exceptions.AuthenticationFailed("令牌缺少用户标识，请重新登录")
    try:
        user = UserModel.objects.get(pk=user_id)
    except UserModel.DoesNotExist:
        raise exceptions.AuthenticationFailed("用户不存在，请重新登录") from None
    bound = refresh.get(PWD_VER_CLAIM)
    if bound != password_fingerprint(user):
        # claim 缺失（部署前存量 token）与密码已变更同口径处理
        raise exceptions.AuthenticationFailed("登录态已失效，请重新登录")


class PasswordBoundTokenObtainPairInputSchema(TokenObtainPairInputSchema):
    """/token/pair — 签发时绑定密码指纹。"""

    @classmethod
    def get_token(cls, user: Any) -> dict[str, str]:
        # cast 修正 mypy 对条件组合类 RefreshToken.for_user 返回类型的误报（实际返回实例）
        refresh = cast(tokens.RefreshToken, tokens.RefreshToken.for_user(user))  # type: ignore[misc]
        bind_password_claim(refresh, user)
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class _PasswordBoundTokenRefreshOutputSchema(TokenRefreshOutputSchema):
    """刷新输出：在标准刷新流程前校验密码绑定。"""

    @model_validator(mode="before")
    @token_error
    def validate_schema(cls, values: Any) -> Any:
        schema_input = SchemaInputService(values, cls.model_config)
        values = schema_input.get_values()

        if isinstance(values, dict):
            if not values.get("refresh"):
                raise exceptions.ValidationError({"refresh": "refresh token is required"})

            refresh = tokens.RefreshToken(values["refresh"])
            verify_password_claim(refresh)

            data: dict[str, Any] = {"access": str(refresh.access_token)}

            if api_settings.ROTATE_REFRESH_TOKENS:
                if api_settings.BLACKLIST_AFTER_ROTATION:
                    try:
                        refresh.blacklist()
                    except AttributeError:
                        # 未安装 blacklist app 时无该方法，跳过
                        pass
                refresh.set_jti()
                refresh.set_exp()
                refresh.set_iat()

                data["refresh"] = str(refresh)
            values.update(data)
        return values


class PasswordBoundTokenRefreshInputSchema(TokenRefreshInputSchema):
    """/token/refresh — 刷新前校验密码绑定。"""

    @classmethod
    def get_response_schema(cls) -> type[TokenRefreshOutputSchema]:
        return _PasswordBoundTokenRefreshOutputSchema
