"""社交登录平台配置模型。

原先社交登录配置是 ``SystemConfig`` 里 ``SOCIAL_AUTH_*`` 前缀的 19 行 KV
（4 个平台 × 4~5 键），读取层再用适配表拼回结构体。独立成表后一行一个平台，
凭证走 ``EncryptedTextField`` 模型层透明加解密——「密文当密钥发出去」这类
表单层加密的坑（授权页正常、回调换 token 才报 invalid_client）结构性消失。
"""

from __future__ import annotations

from django.db import models

from apps.core.model_fields.encrypted import EncryptedTextField


class SocialAuthProvider(models.Model):
    """一个社交登录平台（如飞书 / GitHub / Google / 微信）的接入配置。"""

    id: int

    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="平台标识",
        help_text="与代码注册的 Provider 名一致：feishu / wechat / github / google",
    )
    display_name = models.CharField(max_length=50, verbose_name="显示名称", help_text="登录页按钮上的文案")
    client_id = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="App ID / Client ID",
        help_text=(
            "平台侧应用的客户端 ID。留空且平台支持共用凭证时自动借用"
            "（飞书扫码登录复用「系统配置 → 飞书配置」的 FEISHU_APP_ID，无需重复填写）"
        ),
    )
    client_secret = EncryptedTextField(
        blank=True,
        default="",
        verbose_name="App Secret",
        help_text="平台侧应用的客户端密钥，加密存储；留空且平台支持共用凭证时自动借用",
    )
    redirect_uri = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="回调地址",
        help_text=(
            "后端可达地址（含协议 + Host + 路径，不是前端页面地址），"
            "必须与开放平台后台登记的完全一致——后缀、结尾斜杠差一点都会被平台拒绝。"
            "例：http://127.0.0.1:8002/social/github/callback/。"
            "上线换域名后须同步修改此处与平台后台"
        ),
    )
    scope = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="授权范围",
        help_text="空格分隔，留空用平台默认。例：read:user user:email",
    )
    enabled = models.BooleanField(default=True, verbose_name="启用", help_text="关闭后登录页立即隐藏该入口")
    priority = models.PositiveIntegerField(default=10, verbose_name="排序", help_text="登录页按钮顺序，小的在前")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["priority", "name"]
        verbose_name = "社交登录"
        verbose_name_plural = "社交登录"

    def __str__(self) -> str:
        return f"{self.display_name}({self.name})"
