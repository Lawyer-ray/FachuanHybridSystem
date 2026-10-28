"""一张网案件详情（ajxq）P1 扩展的单元测试。

覆盖：
1. `_parse_case_data` 对新增字段（开庭 / 一审关联 / 承办法官）的解析
2. `_parse_epoch_ms` 的毫秒时间戳边界
3. `service._sync_previous_case` 的一审关联策略（强匹配、不覆盖人工选择）
4. `service._sync_hearing_reminder` 的开庭提醒幂等
5. `_fill_blank_case_fields` 返回真实字段名（回归：曾把中文名传给 update_fields）
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

from plugins.court_automation.case_sync.client import (
    YizhangwangCaseData,
    YizhangwangMember,
    _parse_case_data,
    _parse_epoch_ms,
)
from plugins.court_automation.case_sync.service import (
    _fill_blank_case_fields,
    _sync_hearing_reminder,
    _sync_previous_case,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# 详情解析
# ---------------------------------------------------------------------------


def _payload(**ajvo: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ah": "（20XX）粤01行终某某号",
        "ajmc": "张某与某局行政处罚及行政复议",
        "laaymc": ["行政处罚"],
        "fydmTranslateText": "广东省深圳市中级人民法院",
        "cbsptTranslateText": "行政审判庭",
        "ysah": "（20XX）粤01民初某某号",
        "ysajbh": "258320250401001596",
        "ysfyTranslateText": "深圳市盐田区人民法院",
        "cbrTranslateText": "某某法官",
        "ktsj": 1794274200000,
        "ktddmc": "行政二十六庭",
        "ktzt": "未开庭",
    }
    base.update(ajvo)
    return {"ajVO": base, "spzzcyList": [{"xm": "某某法官", "jsTranslateText": "审判长"}]}


def test_parse_case_data_reads_p1_fields() -> None:
    data = _parse_case_data("aj-1", _payload())

    assert data.case_number == "（20XX）粤01行终某某号"
    assert data.cause_of_action == "行政处罚"
    assert data.court_name == "广东省深圳市中级人民法院"
    assert data.tribunal == "行政审判庭"

    # P1：开庭
    assert data.hearing_at is not None
    assert (data.hearing_at.hour, data.hearing_at.minute) == (9, 30)
    assert data.hearing_room == "行政二十六庭"
    assert data.hearing_status == "未开庭"

    # P1：一审关联
    assert data.first_instance_number == "（20XX）粤01民初某某号"
    assert data.first_instance_ajbh == "258320250401001596"
    assert data.first_instance_court == "深圳市盐田区人民法院"

    # P1：承办法官
    assert data.judge == "某某法官"

    assert [m.name for m in data.members] == ["某某法官"]


def test_parse_case_data_tolerates_empty_fields() -> None:
    """一张网大量字段为空串 / 0，解析不能抛异常。"""
    data = _parse_case_data("aj-2", {"ajVO": {"ah": "", "ktsj": 0, "ktddmc": None, "ysah": None}})

    assert data.case_number == ""
    assert data.hearing_at is None
    assert data.hearing_room == ""
    assert data.first_instance_number == ""
    assert data.members == []


def test_parse_epoch_ms_boundaries() -> None:
    assert _parse_epoch_ms(1794274200000) is not None
    for bad in (0, None, "", -1, "abc", [], {}):
        assert _parse_epoch_ms(bad) is None


# ---------------------------------------------------------------------------
# 前序案件关联
# ---------------------------------------------------------------------------


def _case_data(**overrides: Any) -> YizhangwangCaseData:
    base: dict[str, Any] = {
        "ajbh": "aj-new",
        "case_number": "（20XX）粤01行终某某号",
        "first_instance_number": "（20XX）粤01民初某某号",
        "first_instance_ajbh": "ys-ajbh-1",
        "members": [YizhangwangMember(name="某某法官", title="审判长", role="presiding_judge")],
    }
    base.update(overrides)
    return YizhangwangCaseData(**base)


def test_sync_previous_case_links_by_yizhangwang_id(db: Any) -> None:
    """一审案件标识命中时优先按 yz_wid 关联。"""
    from apps.cases.models import Case

    previous = Case.objects.create(yz_wid="ys-ajbh-1", name="一审案件")
    current = Case.objects.create(yz_wid="aj-new", name="二审案件")

    note = _sync_previous_case(current, _case_data())

    current.refresh_from_db()
    assert current.previous_case_id == previous.pk
    assert "已关联前序案件" in note


def test_sync_previous_case_falls_back_to_case_number(db: Any) -> None:
    """没有 yz_wid 命中时，按一审案号匹配。"""
    from apps.cases.models import Case, CaseNumber

    previous = Case.objects.create(yz_wid="", name="一审案件")
    CaseNumber.objects.create(case=previous, number="（20XX）粤01民初某某号")
    current = Case.objects.create(yz_wid="aj-new", name="二审案件")

    _sync_previous_case(current, _case_data(first_instance_ajbh=""))

    current.refresh_from_db()
    assert current.previous_case_id == previous.pk


def test_sync_previous_case_does_not_overwrite_manual_choice(db: Any) -> None:
    """人工已选的前序案件不被同步覆盖。"""
    from apps.cases.models import Case

    manual = Case.objects.create(yz_wid="manual-prev", name="人工选的前序")
    other = Case.objects.create(yz_wid="ys-ajbh-1", name="一张网认为的前序")
    current = Case.objects.create(yz_wid="aj-new", name="二审案件", previous_case=manual)

    note = _sync_previous_case(current, _case_data())

    current.refresh_from_db()
    assert current.previous_case_id == manual.pk
    assert note == ""


def test_sync_previous_case_reports_missing_local_case(db: Any) -> None:
    """本地没有一审案件时不自动新建，只给提示文案。"""
    from apps.cases.models import Case

    current = Case.objects.create(yz_wid="aj-new", name="二审案件")

    note = _sync_previous_case(current, _case_data())

    current.refresh_from_db()
    assert current.previous_case_id is None
    assert "本地未找到对应案件" in note


# ---------------------------------------------------------------------------
# 开庭提醒
# ---------------------------------------------------------------------------


def test_sync_hearing_reminder_creates_once(db: Any) -> None:
    """同一案件同一开庭时刻只建一条提醒（重复同步不重复建）。"""
    from apps.cases.models import Case
    from apps.reminders.models import Reminder, ReminderType

    case = Case.objects.create(yz_wid="aj-h", name="有开庭的案件")
    data = _case_data(hearing_at=_parse_epoch_ms(1794274200000), hearing_room="第三法庭")

    first = _sync_hearing_reminder(case, data)
    second = _sync_hearing_reminder(case, data)

    assert first.startswith("开庭")
    assert second == ""

    reminders = Reminder.objects.filter(case=case, reminder_type=ReminderType.HEARING)
    assert reminders.count() == 1
    reminder = reminders.first()
    assert reminder is not None
    assert reminder.metadata["source"] == "yizhangwang"
    assert reminder.metadata["courtroom"] == "第三法庭"


def test_sync_hearing_reminder_skips_without_time(db: Any) -> None:
    from apps.cases.models import Case
    from apps.reminders.models import Reminder

    case = Case.objects.create(yz_wid="aj-nh", name="无开庭的案件")

    assert _sync_hearing_reminder(case, _case_data(hearing_at=None)) == ""
    assert Reminder.objects.filter(case=case).count() == 0


# ---------------------------------------------------------------------------
# 回归：update_fields 必须是真实字段名
# ---------------------------------------------------------------------------


def test_fill_blank_case_fields_returns_real_field_names(db: Any) -> None:
    """回归：曾把中文展示名直接传给 save(update_fields=...)，会 ValueError。"""
    from apps.cases.models import Case

    case = Case.objects.create(name="", cause_of_action="")
    data = _case_data(cause_of_action="买卖合同纠纷", case_name="张某与某公司纠纷")

    changed, labels = _fill_blank_case_fields(case, data)

    assert set(changed) == {"cause_of_action", "name"}
    assert set(labels) == {"案由", "案件名称"}
    # 真实字段名必须能用于 save
    case.save(update_fields=changed)
    case.refresh_from_db()
    assert case.cause_of_action == "买卖合同纠纷"
    assert case.name == "张某与某公司纠纷"
