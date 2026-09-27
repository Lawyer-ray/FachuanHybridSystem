"""默认系统配置的数据约束。

「初始化默认配置」会把 ``get_default_configs()`` 的每一行写进 ``SystemConfig``，
而 ``description`` 是 ``varchar(255)`` —— 写超了会在插入时抛
``DataError: value too long``，且失败点往往落在「注册首个用户」这类看着不相关的
地方（``FirstUserSetupService`` 会顺带初始化默认配置），排查成本很高。

2026-09-27 实际踩过：新增的 ``SOCIAL_AUTH_GOOGLE_REDIRECT_URI`` 描述写到 272 字符，
导致 ``test_register_first_user_with_token_prod`` 等三个 organization 用例失败，
报错信息里完全看不出是配置描述的问题。这里把它钉死。
"""

from __future__ import annotations

from apps.core.admin._system_config_data import get_default_configs
from apps.core.models import SystemConfig


class TestDefaultConfigsIntegrity:
    def test_description_fits_column(self) -> None:
        max_length = SystemConfig._meta.get_field("description").max_length
        assert max_length is not None

        too_long = [
            (item["key"], len(item["description"])) for item in get_default_configs() if len(item["description"]) > max_length
        ]
        assert too_long == [], f"description 超过 varchar({max_length})，初始化时会 DataError：{too_long}"

    def test_keys_are_unique(self) -> None:
        """SystemConfig.key 全局唯一。

        默认数据里出现重复 key 时会退化成「谁后写谁生效」，
        排查时只看到某个配置莫名不对，看不出是数据源重复。
        """
        keys = [item["key"] for item in get_default_configs()]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        assert duplicates == [], f"默认配置存在重复 key：{duplicates}"

    def test_social_auth_keys_carry_prefix(self) -> None:
        """社交登录的键必须带 SOCIAL_AUTH_ 前缀。

        该分类要复用「飞书配置」里的 FEISHU_APP_ID / FEISHU_APP_SECRET，而
        SystemConfig.key 全局唯一 —— 少了前缀就会与 IM 分类撞名。
        """
        missing = [
            item["key"]
            for item in get_default_configs()
            if item["category"] == "social_auth" and not item["key"].startswith("SOCIAL_AUTH_")
        ]
        assert missing == [], f"social_auth 配置缺少 SOCIAL_AUTH_ 前缀：{missing}"
