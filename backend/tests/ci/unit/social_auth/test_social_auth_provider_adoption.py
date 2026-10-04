"""SystemConfig → SocialAuthProvider 收养迁移（0006）的行为锁定。

迁移在生产库上只跑一次，但它搬的是登录凭证（如已写库的 GitHub Client ID），
搬错 = 登录功能断，必须单测兜住：字段映射、enabled 字符串、密文解密、旧行清理。
"""

from __future__ import annotations

import pytest
from django.apps import apps as django_apps

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec
from apps.social_auth.migrations._adopt_helpers import adopt_social_auth_configs
from apps.social_auth.models import SocialAuthProvider


@pytest.mark.django_db
class TestAdoptSocialAuthConfigs:
    def _seed_legacy_rows(self, *, github_secret: str = "gh-plain-secret") -> None:
        """模拟迁移前的 SystemConfig 布局（含密文 secret）。"""
        encrypted_secret = SecretCodec().encrypt("gh-plain-secret") if github_secret == "encrypted" else github_secret
        SystemConfig.objects.bulk_create(
            [
                SystemConfig(key="SOCIAL_AUTH_FEISHU_APP_ID", value="", category="social_auth"),
                SystemConfig(key="SOCIAL_AUTH_FEISHU_APP_SECRET", value="", category="social_auth"),
                SystemConfig(
                    key="SOCIAL_AUTH_FEISHU_REDIRECT_URI",
                    value="http://127.0.0.1:8002/social/feishu/callback/",
                    category="social_auth",
                ),
                SystemConfig(
                    key="SOCIAL_AUTH_FEISHU_SCOPE", value="contact:user.base:readonly", category="social_auth"
                ),
                SystemConfig(key="SOCIAL_AUTH_FEISHU_ENABLED", value="true", category="social_auth"),
                SystemConfig(key="SOCIAL_AUTH_GITHUB_APP_ID", value="Iv1.client-id-real", category="social_auth"),
                SystemConfig(
                    key="SOCIAL_AUTH_GITHUB_APP_SECRET",
                    value=encrypted_secret,
                    category="social_auth",
                    is_secret=True,
                ),
                SystemConfig(
                    key="SOCIAL_AUTH_GITHUB_REDIRECT_URI",
                    value="http://localhost:8002/social/github/callback/",
                    category="social_auth",
                ),
                SystemConfig(key="SOCIAL_AUTH_GITHUB_SCOPE", value="read:user user:email", category="social_auth"),
                SystemConfig(key="SOCIAL_AUTH_GITHUB_ENABLED", value="true", category="social_auth"),
                SystemConfig(key="SOCIAL_AUTH_WECHAT_ENABLED", value="false", category="social_auth"),
                # 与社交登录无关的行，收养后必须保留
                SystemConfig(key="FEISHU_APP_ID", value="cli_shared", category="feishu"),
                SystemConfig(key="SOME_OTHER_KEY", value="v", category="general"),
            ]
        )

    def test_adopts_fields_and_deletes_legacy_rows(self) -> None:
        self._seed_legacy_rows()

        adopt_social_auth_configs(django_apps, None)

        github = SocialAuthProvider.objects.get(name="github")
        assert github.client_id == "Iv1.client-id-real"
        assert github.client_secret == "gh-plain-secret"  # pragma: allowlist secret
        assert github.redirect_uri == "http://localhost:8002/social/github/callback/"
        assert github.scope == "read:user user:email"
        assert github.enabled is True
        assert github.priority == 20

        feishu = SocialAuthProvider.objects.get(name="feishu")
        assert feishu.client_id == ""
        assert feishu.redirect_uri == "http://127.0.0.1:8002/social/feishu/callback/"

        wechat = SocialAuthProvider.objects.get(name="wechat")
        assert wechat.enabled is False

        # 旧 social_auth 分类行全删；其它分类原样保留
        assert not SystemConfig.objects.filter(category="social_auth").exists()
        assert SystemConfig.objects.filter(key="FEISHU_APP_ID").exists()
        assert SystemConfig.objects.filter(key="SOME_OTHER_KEY").exists()

    def test_decrypts_encrypted_secret(self) -> None:
        """旧 KV 里 admin 保存过的 secret 是密文，收养后新表里应是可读明文（再由字段层加密落库）。"""
        self._seed_legacy_rows(github_secret="encrypted")  # pragma: allowlist secret

        adopt_social_auth_configs(django_apps, None)

        github = SocialAuthProvider.objects.get(name="github")
        assert github.client_secret == "gh-plain-secret"  # pragma: allowlist secret

    def test_adopt_is_idempotent(self) -> None:
        """重复执行不报错、不产生重复行（update_or_create 语义）。"""
        self._seed_legacy_rows()
        adopt_social_auth_configs(django_apps, None)
        # 第二次执行时旧行已删，等价于无旧数据的空跑
        adopt_social_auth_configs(django_apps, None)

        assert SocialAuthProvider.objects.filter(name="github").count() == 1

    def test_noop_when_no_legacy_rows(self) -> None:
        """全新环境（无 social_auth 分类行）执行收养是安全的空操作。

        0007 起迁移会为微软插入默认行，所以「全新环境」不再等于表为空——
        空操作的判据是「不新增任何收养行」。
        """
        before = set(SocialAuthProvider.objects.values_list("name", flat=True))
        adopt_social_auth_configs(django_apps, None)

        assert set(SocialAuthProvider.objects.values_list("name", flat=True)) == before

    def test_bad_ciphertext_treated_as_unconfigured(self) -> None:
        """解不开的密文按「未配置」处理，绝不把密文搬进新表当明文。"""
        SystemConfig.objects.bulk_create(
            [
                SystemConfig(key="SOCIAL_AUTH_GITHUB_APP_ID", value="Iv1.x", category="social_auth"),
                SystemConfig(
                    key="SOCIAL_AUTH_GITHUB_APP_SECRET", value="enc:v1:not-a-valid-token", category="social_auth"
                ),
            ]
        )

        adopt_social_auth_configs(django_apps, None)

        github = SocialAuthProvider.objects.get(name="github")
        assert github.client_secret == ""
