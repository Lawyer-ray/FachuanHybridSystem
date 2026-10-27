"""organization 0012 迁移：LawFirm.name 唯一约束 + 并发安全的 get_or_create。

背景：`LawFirm` 的去重完全依赖 `get_or_create(name=...)`（律师导入 4 处），
但 name 没有数据库唯一约束。并发导入会造出同名重复律所；而 `Team` 的唯一键是
`(law_firm, team_type, name)`——律所一旦重复，同一团队会被拆成两条，取团队
成员时漏人。

本测试钉三件事：
1. 数据库层面 name 已唯一（ORM 直接插重复行会被拒）；
2. 迁移前置检查函数在重复数据上会**带可操作清单**报错（用假 registry 构造重复，
   不依赖 DDL，避免在 pytest 事务内改表结构）；
3. `get_or_create_law_firm` 撞唯一约束时能取回已有行，不冒泡。
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest
from django.db import IntegrityError

from apps.organization.models import LawFirm
from apps.organization.services.lawyer_import_service import get_or_create_law_firm

_migration_0012 = import_module("apps.organization.migrations.0012_lawfirm_name_unique")
assert_no_duplicate_law_firm_names = _migration_0012._assert_no_duplicate_law_firm_names


# ---------------------------------------------------------------------------
# 1. 数据库唯一约束
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_db_rejects_duplicate_name() -> None:
    LawFirm.objects.create(name="唯一律所甲")
    with pytest.raises(IntegrityError):
        # 同一事务内重复插入会被唯一索引拒绝
        LawFirm.objects.create(name="唯一律所甲")


# ---------------------------------------------------------------------------
# 2. 迁移前置检查（用假 registry，不碰真实表结构）
# ---------------------------------------------------------------------------


def _fake_apps(rows: list[tuple[int, str]]) -> MagicMock:
    """构造一个只提供 LawFirm.objects.values_list(...) 的假 Django apps registry。"""
    lawfirm_model = MagicMock()
    lawfirm_model.objects.values_list.return_value.iterator.return_value = iter(rows)
    registry = MagicMock()
    registry.get_model.return_value = lawfirm_model
    return registry


def test_no_duplicates_passes() -> None:
    """无重复时应正常返回（不抛异常），用返回值断言而非空跑。"""
    result = assert_no_duplicate_law_firm_names(_fake_apps([(1, "甲所"), (2, "乙所")]), None)
    assert result is None


def test_duplicates_raise_with_actionable_detail() -> None:
    fake = _fake_apps([(1, "重复律所"), (2, "重复律所"), (3, "独一所")])
    with pytest.raises(RuntimeError) as exc:
        assert_no_duplicate_law_firm_names(fake, None)
    message = str(exc.value)
    assert "重复律所" in message
    assert "ids=[1, 2]" in message
    assert "合并" in message  # 给出可操作的处置指引


# ---------------------------------------------------------------------------
# 3. 并发安全 helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_or_create_law_firm_returns_existing() -> None:
    firm = LawFirm.objects.create(name="已存在律所")
    got, created = get_or_create_law_firm("已存在律所")
    assert got.pk == firm.pk
    assert created is False


@pytest.mark.django_db
def test_get_or_create_law_firm_creates_new() -> None:
    got, created = get_or_create_law_firm("新律所")
    assert created is True
    assert got.name == "新律所"


@pytest.mark.django_db
def test_get_or_create_law_firm_survives_concurrent_unique_conflict() -> None:
    """模拟并发：get_or_create 撞 IntegrityError，应回查并返回已有行而非冒泡。"""
    other = LawFirm.objects.create(name="并发律所")

    with patch("apps.organization.services.lawyer_import_service.LawFirm.objects.get_or_create") as mocked:
        mocked.side_effect = IntegrityError("duplicate key value violates unique constraint")
        got, created = get_or_create_law_firm("并发律所")

    assert got.pk == other.pk
    assert created is False
