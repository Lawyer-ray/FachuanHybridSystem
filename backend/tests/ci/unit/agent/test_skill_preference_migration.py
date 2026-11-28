"""迁移 0031 的回填/反向函数：``skill_name`` ↔ ``skill_key``（不真跑迁移）。

迁移函数只依赖 ``apps.get_model(...).objects.all()``；用最小 fake 模型把两个方向
都跑一遍——真跑迁移会写真实数据库，本仓库禁止（测试库也只在 pytest 建库时迁移）。
"""

from __future__ import annotations

import importlib
from typing import Any

MIGRATION_NAME = "0031_personal_skills"
migration = importlib.import_module(f"apps.agent.migrations.{MIGRATION_NAME}")


class _Row:
    def __init__(self, skill_key: str = "", skill_name: str = "") -> None:
        self.skill_key = skill_key
        self.skill_name = skill_name
        self.deleted = False
        self.saved_fields: list[str] = []

    def save(self, update_fields: list[str] | None = None) -> None:
        self.saved_fields = list(update_fields or [])

    def delete(self) -> None:
        self.deleted = True


class _Query(list):
    def iterator(self) -> Any:
        return iter(list(self))


class _Manager:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def all(self) -> _Query:
        return _Query(self._rows)


class _FakeApps:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows

    def get_model(self, app_label: str, model_name: str) -> Any:
        assert (app_label, model_name) == ("agent", "AgentSkillPreference")
        rows = self.rows

        class _FakeModel:
            objects = _Manager(rows)

        return _FakeModel


def test_forward_backfills_builtin_prefix() -> None:
    rows = [_Row(skill_name="web-research"), _Row(skill_name="deadline-queries")]
    migration.backfill_skill_key(_FakeApps(rows), None)
    assert [row.skill_key for row in rows] == ["builtin:web-research", "builtin:deadline-queries"]
    assert all(row.saved_fields == ["skill_key"] for row in rows)


def test_reverse_strips_prefix_and_drops_personal_keys() -> None:
    builtin = _Row(skill_key="builtin:web-research")
    personal = _Row(skill_key="skill:8f3a0c1e-0000-0000-0000-000000000000")
    migration.restore_skill_name(_FakeApps([builtin, personal]), None)
    assert builtin.skill_name == "web-research"
    assert builtin.saved_fields == ["skill_name"]
    assert personal.deleted is True
    assert personal.saved_fields == []


def test_migration_id_is_0031_and_depends_on_ui_action_0030() -> None:
    """迁移号是硬约定：0030 被并行 lane 的 ui_action 唯一索引占走（同分支已提交），本迁移排 0031。"""
    assert migration.Migration.dependencies[0] == ("agent", "0030_uiaction_unsettled_unique")


def test_reverse_is_safe_with_existing_rows() -> None:
    """反向移除 ``skill_name`` 时必须有默认值，否则有存量行必炸。

    ``RemoveField`` 的逆向是 ``AddField``，字段定义取自它**前一步的迁移状态**。
    0014 的 ``skill_name`` 是 ``blank=False`` 且无默认，Django 会生成
    ``ADD COLUMN ... NOT NULL``（无 DEFAULT）——空表能过，表里有偏好行时
    ``NotNullViolation``，反向迁移整体失败。

    守的是「结构」而不是「DDL」：断言 RemoveField 前一步把该字段改成了带默认值的
    形态。真正的 DDL 反向在一次性库上实跑过（见 changelog v27.31.0）。
    """
    operations = list(migration.Migration.operations)
    remove_at = next(
        i
        for i, op in enumerate(operations)
        if op.__class__.__name__ == "RemoveField"
        and getattr(op, "model_name", None) == "agentskillpreference"
        and getattr(op, "name", None) == "skill_name"
    )
    previous = operations[remove_at - 1]
    assert previous.__class__.__name__ == "AlterField", "RemoveField 之前必须紧跟 AlterField(skill_name)"
    assert getattr(previous, "name", None) == "skill_name"
    assert previous.field.has_default(), "skill_name 的迁移状态必须带默认值，否则反向 AddField 生成 NOT NULL 无 DEFAULT 列"
    assert previous.field.blank, "同时要允许空串回填"
