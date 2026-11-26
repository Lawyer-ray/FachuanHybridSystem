"""界面上的配置说明以**代码**为准，不以库里的 `SystemConfig.description` 为准。

## 为什么需要这组用例

`SystemConfigAdmin.init_defaults_view` 用 `get_or_create(key=..., defaults=...)`——
**已存在的行一个字段都不会更新**。于是「改了 `_system_config_data/*.py` 里的文案」对存量
部署等于白改：dev/线上看到仍是旧话，而代码里看着一切正确。更糟的是库里那句能被手改
（实测有人把「走 L1」写成「见 L1」），按设计跳过被改过行的 data migration 也救不回来，
旧版假话（「留空则判定一律落人工」）就一直挂在界面上。

所以展示层改成「代码文案优先，库里那份只在代码里没有这个键时兜底」，取值只有一个入口：
`apps.core.services.system_config_admin_service.code_description_of`。

库里的列还在，但它从此只是「兜底 + 部署备注」：代码里有这个键时既不展示、也不被表单回写。

数据全部虚构，不含任何真实凭证。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from apps.core.admin._system_config_data import get_default_configs
from apps.core.models import SystemConfig
from apps.core.services.system_config_admin_service import clear_code_description_cache, code_description_of

pytestmark = pytest.mark.django_db

#: 只存在于本用例伪造的「代码」里。
FAKE_KEY = "TEST_DESC_AUTHORITY_KEY"
#: 「代码」里没有的键：走库列兜底的那条路。
NO_CODE_KEY = "TEST_DESC_NO_CODE_KEY"

CODE_TEXT = "代码里的说明：证件/账号类字段不走打分器，走 L1 校验位。"
NEWER_CODE_TEXT = "代码里又改了一遍：分歧全部进人工清单。"
#: 库里那句旧版假话（真实事故里的措辞）。
STALE_DB_TEXT = "留空则判定一律落人工。"
#: 管理员自己写在库里的部署备注。
CUSTOM_DB_TEXT = "本所自定：交接期间先别开。"

#: 「说明由代码维护」的提示语（编辑页必须出现，否则人会一直在库里改一个不生效的副本）。
MAINTAINED_HINT = "本说明由代码维护"


@pytest.fixture(autouse=True)
def _fresh_code_description_cache() -> Iterator[None]:
    """索引是模块级缓存：每条用例前后各清一次，用例之间不互相污染。"""
    clear_code_description_cache()
    yield
    clear_code_description_cache()


def _patch_code_defaults(monkeypatch: pytest.MonkeyPatch, description: str) -> None:
    """把「代码里登记的默认配置」换成一条测试专属条目。

    补的就是 `code_description_of` 读的那个来源：它一变，界面文案就该跟着变。
    """
    monkeypatch.setattr(
        "apps.core.services.system_config_admin_service.get_default_configs",
        lambda: [{"key": FAKE_KEY, "category": "general", "description": description, "value": ""}],
    )


@pytest.fixture()
def code_defaults(monkeypatch: pytest.MonkeyPatch) -> str:
    """代码里登记 `FAKE_KEY` 的说明；`NO_CODE_KEY` 不在代码里，正好当兜底路径的对照。"""
    _patch_code_defaults(monkeypatch, CODE_TEXT)
    return CODE_TEXT


def _row(key: str, description: str) -> SystemConfig:
    return SystemConfig.objects.create(key=key, category="general", description=description, value="v1")


def _change_url(row: SystemConfig) -> str:
    return f"/admin/core/systemconfig/{row.pk}/change/"


class TestCodeDescriptionOf:
    """唯一权威入口本身的行为。"""

    def test_代码里登记过的键返回代码文案(self, code_defaults: str) -> None:
        assert code_description_of(FAKE_KEY) == code_defaults

    def test_代码里没有的键返回None(self, code_defaults: str) -> None:
        assert code_description_of(NO_CODE_KEY) is None

    def test_读的是种子里的原话(self) -> None:
        """不 patch 时取到的必须就是 `get_default_configs()` 里那一句（不另抄一份）。"""
        expected = next(
            str(item["description"]) for item in get_default_configs() if str(item["key"]) == "OCR_JUDGE_ENABLED"
        )

        assert code_description_of("OCR_JUDGE_ENABLED") == expected

    def test_种子变了必须清缓存才生效(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """索引是模块级缓存：不清就还返回旧文案，清缓存入口就是为这种变更场景准备的。"""
        _patch_code_defaults(monkeypatch, CODE_TEXT)
        clear_code_description_cache()
        assert code_description_of(FAKE_KEY) == CODE_TEXT

        _patch_code_defaults(monkeypatch, NEWER_CODE_TEXT)
        assert code_description_of(FAKE_KEY) == CODE_TEXT

        clear_code_description_cache()
        assert code_description_of(FAKE_KEY) == NEWER_CODE_TEXT


class TestEditPageDescription:
    """编辑页：代码里有这个键 → 只读 + 显示代码文案；没有 → 原样可编辑。"""

    def test_显示代码文案而不是库里的旧假话(self, client: Any, admin_user: Any, code_defaults: str) -> None:
        row = _row(FAKE_KEY, STALE_DB_TEXT)
        client.force_login(admin_user)

        body = client.get(_change_url(row)).content.decode()

        assert CODE_TEXT in body
        assert STALE_DB_TEXT not in body

    def test_只渲染不写库(self, client: Any, admin_user: Any, code_defaults: str) -> None:
        row = _row(FAKE_KEY, STALE_DB_TEXT)
        client.force_login(admin_user)

        assert client.get(_change_url(row)).status_code == 200

        row.refresh_from_db()
        assert row.description == STALE_DB_TEXT

    def test_代码里的键描述只读(self, client: Any, admin_user: Any, code_defaults: str) -> None:
        row = _row(FAKE_KEY, STALE_DB_TEXT)
        client.force_login(admin_user)

        body = client.get(_change_url(row)).content.decode()

        assert 'name="description"' not in body
        assert '<div class="readonly">' in body
        assert MAINTAINED_HINT in body

    def test_代码里没有的键仍可编辑并显示库里文案(self, client: Any, admin_user: Any, code_defaults: str) -> None:
        row = _row(NO_CODE_KEY, CUSTOM_DB_TEXT)
        client.force_login(admin_user)

        body = client.get(_change_url(row)).content.decode()

        assert 'name="description"' in body
        assert CUSTOM_DB_TEXT in body
        assert MAINTAINED_HINT not in body

    def test_代码文案再改一次界面跟着变(
        self, client: Any, admin_user: Any, code_defaults: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """库列一个字都不动、只改代码 → 页面必须跟着变，否则又是「改了代码＝白改」。"""
        row = _row(FAKE_KEY, STALE_DB_TEXT)
        client.force_login(admin_user)
        assert CODE_TEXT in client.get(_change_url(row)).content.decode()

        _patch_code_defaults(monkeypatch, NEWER_CODE_TEXT)
        clear_code_description_cache()
        body = client.get(_change_url(row)).content.decode()

        assert NEWER_CODE_TEXT in body
        assert CODE_TEXT not in body
        row.refresh_from_db()
        assert row.description == STALE_DB_TEXT

    def test_保存不会把代码文案写回库列(self, client: Any, admin_user: Any, code_defaults: str) -> None:
        """描述只读＝不在表单里：改别的字段保存，库里那句部署备注一个字都不该动。"""
        row = _row(FAKE_KEY, STALE_DB_TEXT)
        client.force_login(admin_user)

        response = client.post(
            _change_url(row),
            {
                "key": FAKE_KEY,
                "value": "v2",
                "category": "general",
                # 就算有人手工把提交塞满，也不该落进库（字段被 get_readonly_fields 排除）
                "description": CODE_TEXT,
                "is_active": "on",
            },
        )

        assert response.status_code == 302
        row.refresh_from_db()
        assert row.value == "v2"
        assert row.description == STALE_DB_TEXT


class TestChangelistCardDescription:
    """列表页分组卡片：说明同样以代码为准。"""

    def test_卡片用代码文案(self, client: Any, admin_user: Any, code_defaults: str) -> None:
        _row(FAKE_KEY, STALE_DB_TEXT)
        client.force_login(admin_user)

        body = client.get("/admin/core/systemconfig/").content.decode()

        assert CODE_TEXT in body
        assert STALE_DB_TEXT not in body

    def test_代码里没有的键卡片显示库里文案(self, client: Any, admin_user: Any, code_defaults: str) -> None:
        _row(NO_CODE_KEY, CUSTOM_DB_TEXT)
        client.force_login(admin_user)

        body = client.get("/admin/core/systemconfig/").content.decode()

        assert CUSTOM_DB_TEXT in body
