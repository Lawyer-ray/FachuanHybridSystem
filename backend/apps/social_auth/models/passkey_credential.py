"""通行密钥（Passkey/WebAuthn）凭据。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class PasskeyCredential(models.Model):
    """一条已注册的通行密钥（authenticator 上的公钥凭据）。

    只存公钥侧信息：私钥永远留在用户设备的安全芯片里（Touch ID / Windows Hello），
    服务器被拖库也造不出可用凭据。

    ``rp_id`` 记录注册时的生效域（如 ``localhost`` / ``app.xlaw.top``）：
    WebAuthn 凭据按 RP ID 隔离，同一把 Touch ID 在两个域要各注册一次，
    登录时必须用与注册相同的域名访问。
    """

    id: int
    user = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="passkey_credentials",
        verbose_name="用户",
    )
    name = models.CharField(max_length=100, default="通行密钥", verbose_name="名称")
    # 浏览器/认证器生成的唯一凭据 ID，base64url 编码（典型 43~200 字符）
    credential_id = models.CharField(max_length=512, unique=True, verbose_name="凭据ID")
    # 认证器公钥（COSE 格式），base64url 编码——验签的信任锚，不含任何秘密
    public_key = models.TextField(verbose_name="公钥")
    # 认证器签名计数器：必须单调递增，回退意味着凭据被克隆
    sign_count = models.PositiveBigIntegerField(default=0, verbose_name="签名计数")
    rp_id = models.CharField(max_length=255, verbose_name="RP ID")
    backed_up = models.BooleanField(default=False, verbose_name="可同步备份")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name="最近使用")

    class Meta:
        verbose_name = "通行密钥"
        verbose_name_plural = "通行密钥"
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name}({self.rp_id}) → {self.user}"
