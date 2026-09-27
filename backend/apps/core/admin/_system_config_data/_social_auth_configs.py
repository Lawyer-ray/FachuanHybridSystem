"""社交登录 Provider 配置数据

配置规范：
- 每个 Provider 一个配置分组，键名统一加 ``SOCIAL_AUTH_`` 前缀。
  ``SystemConfig.key`` 是全局唯一的，不能和 IM 群聊分类（``feishu``）下的
  ``FEISHU_APP_ID`` 重名，所以这里用 ``SOCIAL_AUTH_FEISHU_*``。
- **凭证复用**：扫码登录与 IM 群聊共用同一个飞书自建应用，因此
  ``SOCIAL_AUTH_FEISHU_APP_ID`` / ``APP_SECRET`` 留空即自动读取「飞书配置」
  分类下的同名凭证，不需要重复填写。仅当扫码要改用独立应用时才在这里填。
- ``redirect_uri`` 必须在飞书开发者后台「安全设置」中精确登记（``?``/``#`` 后缀会被忽略），
  否则授权页直接返回 ``{"code": 2000, "message": "redirect_uri unmatch"}``。
- 扫描完二维码由飞书 302 打回该地址，所以它必须是**后端**可达地址（含协议+Host+路径），
  不能是前端页面地址。
"""

from typing import Any

__all__ = ["get_social_auth_configs"]


def get_social_auth_configs() -> list[dict[str, Any]]:
    """获取社交登录配置项"""
    return [
        # ============ 飞书扫码登录 ============
        {
            "key": "SOCIAL_AUTH_FEISHU_APP_ID",
            "category": "social_auth",
            "description": (
                "飞书应用 App ID。留空则复用「飞书配置」里的 FEISHU_APP_ID"
                "（扫码登录与案件群聊共用同一应用，通常无需在此重复填写）"
            ),
            "value": "",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_FEISHU_APP_SECRET",
            "category": "social_auth",
            "description": (
                "飞书应用 App Secret。留空则复用「飞书配置」里的 FEISHU_APP_SECRET；仅当扫码改用独立应用时才填"
            ),
            "value": "",
            "is_secret": True,
        },
        {
            "key": "SOCIAL_AUTH_FEISHU_REDIRECT_URI",
            "category": "social_auth",
            "description": (
                "飞书授权回调地址。需在开发者后台「开发配置 → 安全设置 → 重定向 URL」中精确登记，"
                "并且是后端可达地址，例如 http://127.0.0.1:8002/social/feishu/callback/。"
                "上线换域名后必须同步修改此处与飞书后台。"
            ),
            "value": "http://127.0.0.1:8002/social/feishu/callback/",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_FEISHU_SCOPE",
            "category": "social_auth",
            "description": (
                "授权范围，空格分隔。最小集 contact:user.base:readonly 可获取昵称、头像、union_id；"
                "如需邮箱需追加对应权限，但飞书明确建议不要直接用邮箱作为业务系统登录凭据。"
            ),
            "value": "contact:user.base:readonly",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_FEISHU_ENABLED",
            "category": "social_auth",
            "description": "是否启用飞书扫码登录（填 false 可临时下线该登录方式）",
            "value": "true",
            "is_secret": False,
        },
        # ============ 微信扫码登录 ============
        {
            "key": "SOCIAL_AUTH_WECHAT_APP_ID",
            "category": "social_auth",
            "description": "微信开放平台网站应用 AppID（未配置则登录页不显示微信入口）",
            "value": "",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_WECHAT_APP_SECRET",
            "category": "social_auth",
            "description": "微信开放平台网站应用 AppSecret（请勿泄露）",
            "value": "",
            "is_secret": True,
        },
        {
            "key": "SOCIAL_AUTH_WECHAT_REDIRECT_URI",
            "category": "social_auth",
            "description": (
                "微信授权回调地址。需与微信开放平台登记的一致，且为后端可达地址，"
                "例如 http://127.0.0.1:8002/social/wechat/callback/。"
            ),
            "value": "",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_WECHAT_ENABLED",
            "category": "social_auth",
            "description": "是否启用微信扫码登录（填 false 可临时下线该登录方式）",
            "value": "true",
            "is_secret": False,
        },
        # ============ Google 登录 ============
        {
            "key": "SOCIAL_AUTH_GOOGLE_APP_ID",
            "category": "social_auth",
            "description": (
                "Google OAuth 2.0 客户端 ID。在 Google Cloud Console → Google Auth Platform → 客户端"
                "创建，应用类型必须选「Web 应用」；未配置则登录页不显示 Google 入口"
            ),
            "value": "",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_GOOGLE_APP_SECRET",
            "category": "social_auth",
            "description": "Google OAuth 2.0 客户端密钥（创建客户端时弹窗内显示一次，请勿泄露）",
            "value": "",
            "is_secret": True,
        },
        {
            "key": "SOCIAL_AUTH_GOOGLE_REDIRECT_URI",
            "category": "social_auth",
            "description": (
                # 注意：SystemConfig.description 是 varchar(255)，必须控制在 255 字符内。
                # 超了会在「初始化默认配置」时 DataError: value too long（2026-09-27 踩过）
                "Google 授权回调地址。必须与 Console 里「已获授权的重定向 URI」完全一致"
                "（精确匹配、无通配符），且为后端可达地址。host 需与浏览器访问前端的 host 一致"
                "（cookie 区分 host），前端用 localhost:5090 时回调须为 "
                "http://localhost:8002/social/google/callback/。正式域名必须 HTTPS。"
            ),
            "value": "http://localhost:8002/social/google/callback/",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_GOOGLE_SCOPE",
            "category": "social_auth",
            "description": (
                "授权范围，空格分隔，必须以 openid 开头。默认 openid email profile 可取到 "
                "sub（账号唯一标识）、邮箱、昵称、头像，均属非敏感范围，无需 Google 审核"
            ),
            "value": "openid email profile",
            "is_secret": False,
        },
        {
            "key": "SOCIAL_AUTH_GOOGLE_ENABLED",
            "category": "social_auth",
            "description": "是否启用 Google 登录（填 false 可临时下线该登录方式）",
            "value": "true",
            "is_secret": False,
        },
    ]
