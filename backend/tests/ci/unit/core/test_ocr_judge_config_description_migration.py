"""迁移 `core/0043`：把多引擎分歧裁定的两项配置说明同步到「已接线」的现状。

## 为什么要为一句文案写测试

`SystemConfigAdmin.init_defaults_view` 用 `get_or_create(key=..., defaults=...)`——
**已存在的行一个字段都不会更新**。所以「改了 `_service_configs.py` 就算改好了」是假的：
本机与线上那份配置的说明一个字都不会变，只有全新部署才看得到。

这条例子的作用是把**种子代码**与**迁移里的文案**焊在一起。两者一旦分叉（有人改了种子
却忘了补迁移，或反过来），真实部署会长期停在旧文案上，而代码里看起来一切正确——
这正是「文档漂移」里最难发现的一类：唯一能发现它的地方就是这里。

数据全部虚构，不含任何真实凭证。
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps

from apps.core.admin._system_config_data._service_configs import get_ocr_configs
from apps.core.models import SystemConfig

#: 模块名以数字开头，只能走 importlib（`from ... import` 语法不接受）。
MIGRATION = importlib.import_module("apps.core.migrations.0043_sync_ocr_judge_config_descriptions")

#: 虚构的「管理员自己写过」的说明：迁移不许覆盖它。
CUSTOM = "本所自定：交接期间先别开"

_ENABLED = "OCR_JUDGE_ENABLED"
_API_KEY = "OCR_JUDGE_API_KEY"  # pragma: allowlist secret —— 这是配置键名，不是密钥本身


def _seed_descriptions() -> dict[str, str]:
    """从**种子代码**取当前默认说明（真实部署里「全新安装」看到的就是这一份）。"""
    return {str(item["key"]): str(item["description"]) for item in get_ocr_configs()}


@pytest.mark.parametrize("key", sorted(MIGRATION._DESCRIPTIONS))
def test_种子文案与迁移文案必须逐字一致(key: str) -> None:
    """分叉的后果：新装看到新文案、存量部署永远停在旧文案，而代码里都「正确」。"""
    old, new = MIGRATION._DESCRIPTIONS[key]
    assert old != new, "迁移的旧文案与新文案相同，等于什么都没做"
    assert _seed_descriptions()[key] == new, (
        f"{key} 的说明改了但迁移没跟上（或反过来）：种子与 0043 的新文案必须逐字相同。"
        "改文案时请同时更新种子与迁移里的新文案。"
    )


def test_旧文案确实带着未接线的措辞() -> None:
    """把「化石」本身钉住：这条迁移存在的唯一理由就是去掉那半句。

    旧说明最后一句是「打开前需先填 OCR_JUDGE_API_KEY，且**主链已接线**（否则开关无效果）」，
    配上当时代码里那句「组件已实现但尚未接线到主链」，读起来就是「开了也没用」。
    如果哪天有人把旧文案改掉，迁移里的 `old` 就再也匹配不到任何行——静默失效，
    所以这里把旧措辞本身也锁住。
    """
    old, new = MIGRATION._DESCRIPTIONS[_ENABLED]
    assert "主链已接线" in old, "旧文案变了 → 迁移的 old 将匹配不到任何行"
    assert "主链已接线" not in new
    # 新文案必须把「两级门禁」这个用户最需要知道的优先级说清楚
    assert "部署级总闸" in new and "任务级开关" in new


@pytest.mark.django_db
class TestMigrationBehaviour:
    """真正的行为：只覆盖「仍是旧默认文案」的行。"""

    @staticmethod
    def _make(key: str, description: str) -> SystemConfig:
        return SystemConfig.objects.create(key=key, category="ocr", description=description, value="")

    def test_只改仍是旧默认文案的行(self) -> None:
        old, new = MIGRATION._DESCRIPTIONS[_ENABLED]
        stale = self._make(_ENABLED, old)
        custom = self._make(_API_KEY, CUSTOM)

        MIGRATION.forwards(django_apps, None)

        stale.refresh_from_db()
        custom.refresh_from_db()
        assert stale.description == new
        # 管理员自己写过的那句是他的判断，迁移没有资格替他重写
        assert custom.description == CUSTOM

    def test_空说明也补上(self) -> None:
        """早期手工建的行 description 为空：同样需要这句真话。"""
        _old, new = MIGRATION._DESCRIPTIONS[_ENABLED]
        row = self._make(_ENABLED, "")

        MIGRATION.forwards(django_apps, None)

        row.refresh_from_db()
        assert row.description == new

    def test_可回滚(self) -> None:
        old, new = MIGRATION._DESCRIPTIONS[_API_KEY]
        row = self._make(_API_KEY, old)

        MIGRATION.forwards(django_apps, None)
        row.refresh_from_db()
        assert row.description == new

        MIGRATION.backwards(django_apps, None)
        row.refresh_from_db()
        assert row.description == old

    def test_幂等(self) -> None:
        """连跑两次不该报错，也不该把新文案改回旧文案。"""
        _old, new = MIGRATION._DESCRIPTIONS[_ENABLED]
        row = self._make(_ENABLED, new)

        MIGRATION.forwards(django_apps, None)
        MIGRATION.forwards(django_apps, None)

        row.refresh_from_db()
        assert row.description == new
