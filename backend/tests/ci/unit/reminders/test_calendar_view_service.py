"""apps/reminders/services/calendar_view_service.py 单元测试。

覆盖真实数据里观察到的合并形态（2026-09-01 / 09-09 / 09-24），
以及 title 取值规则与统计口径。纯逻辑测试，不碰 DB。
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from apps.reminders.services.calendar_view_service import (
    EventKind,
    compute_stats,
    group_by_day,
    merge_events,
    to_event_item,
)

TZ = ZoneInfo("Asia/Shanghai")
TODAY = date(2026, 9, 26)
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=TZ)


def make_reminder(
    reminder_id: int,
    *,
    due_at: str,
    reminder_type: str = "hearing",
    content: str = "某案",
    case_id: int | None = None,
    contract_id: int | None = None,
    case_log_id: int | None = None,
    case_name: str | None = None,
    contract_name: str | None = None,
    case_log: object | None = None,
    metadata: dict | None = None,
) -> SimpleNamespace:
    """造一个够用的 Reminder 替身（只带 to_event_item 会读到的属性）。"""
    return SimpleNamespace(
        id=reminder_id,
        # 带偏移量的保持原样；naive 的按 TZ 解释（与 Django make_aware 语义一致）
        due_at=(lambda d: d if d.tzinfo else d.replace(tzinfo=TZ))(datetime.fromisoformat(due_at)),
        reminder_type=reminder_type,
        content=content,
        metadata=metadata or {},
        case_id=case_id,
        contract_id=contract_id,
        case_log_id=case_log_id,
        case=SimpleNamespace(name=case_name) if case_name else None,
        contract=SimpleNamespace(name=contract_name) if contract_name else None,
        case_log=case_log,
    )


def normalize(*reminders: SimpleNamespace) -> list:
    raws = [to_event_item(r, today=TODAY, now=NOW, tz=TZ) for r in reminders]
    return merge_events(raws)


class TestKindMapping:
    def test_hearing_is_court_and_deadline_type_is_deadline(self) -> None:
        events = normalize(
            make_reminder(1, due_at="2026-09-21T09:30:00+08:00", reminder_type="hearing"),
            make_reminder(2, due_at="2026-09-21T23:59:00+08:00", reminder_type="evidence_deadline"),
        )
        by_id = {e.id: e for e in events}
        assert by_id[1].kind == EventKind.COURT
        assert by_id[2].kind == EventKind.DEADLINE

    def test_unknown_type_falls_back_to_follow(self) -> None:
        """未知类型兜底为 follow（后端新增类型时不会显示成"庭期"）。"""
        events = normalize(
            make_reminder(1, due_at="2026-09-21T10:00:00+08:00", reminder_type="weird_new_type"),
        )
        assert events[0].kind == EventKind.FOLLOW

    def test_other_type_maps_to_meeting(self) -> None:
        events = normalize(
            make_reminder(1, due_at="2026-09-21T10:00:00+08:00", reminder_type="other"),
        )
        assert events[0].kind == EventKind.MEETING


class TestTitleRule:
    def test_target_name_wins_over_content(self) -> None:
        """content 是工作笔记（「明天开庭」）时，必须用关联对象名。"""
        events = normalize(
            make_reminder(
                75,
                due_at="2026-09-24T09:50:00+08:00",
                content="代理升平百货被告开庭",
                case_id=377,
                case_name="兴业银行佛山分行诉升平公司、陈达明金融借款合同纠纷一案",
            ),
        )
        assert events[0].title == "兴业银行佛山分行诉升平公司、陈达明金融借款合同纠纷一案"
        # content 原文仍保留，便于核对
        assert events[0].content == "代理升平百货被告开庭"

    def test_falls_back_to_content_when_unbound(self) -> None:
        """未绑定的提醒没有 target_name，退回 content。"""
        events = normalize(
            make_reminder(
                1,
                due_at="2026-09-24T09:00:00+08:00",
                content="佛山市升平百货有限公司诉啡尝香餐饮租赁合同纠纷一案",
            ),
        )
        assert events[0].title == "佛山市升平百货有限公司诉啡尝香餐饮租赁合同纠纷一案"

    def test_contract_name_used(self) -> None:
        events = normalize(
            make_reminder(
                1,
                due_at="2026-07-23T10:30:00+08:00",
                content="本院定于…",
                contract_id=2,
                contract_name="佛山市顺德区奥创电器有限公司、伍钧乐系列案",
            ),
        )
        assert events[0].title == "佛山市顺德区奥创电器有限公司、伍钧乐系列案"
        assert events[0].target_type == "合同"


class TestMerging:
    def test_same_source_id_merges_lawyers(self) -> None:
        """同 source_id（每位律师各一条）→ 一条，律师姓名聚合。"""
        events = normalize(
            make_reminder(
                69,
                due_at="2026-09-01T07:30:00+00:00",
                case_id=351,
                case_name="广东志承电器诉广东威盛买卖合同纠纷一案",
                metadata={
                    "courtroom": "东莞市第一人民法院 寮步第三审判庭",
                    "time_range": "15:30-16:00",
                    "lawyer_name": "房长波",
                    "source_id": "f060389065d24038bc01cce0a1bf629b",
                },
            ),
            make_reminder(
                70,
                due_at="2026-09-01T07:30:00+00:00",
                case_id=351,
                case_name="广东志承电器诉广东威盛买卖合同纠纷一案",
                metadata={
                    "courtroom": "东莞市第一人民法院 寮步第三审判庭",
                    "time_range": "15:30-16:00",
                    "lawyer_name": "黄崧",
                    "source_id": "f060389065d24038bc01cce0a1bf629b",
                },
            ),
        )
        assert len(events) == 1
        assert events[0].person == "房长波、黄崧"
        assert events[0].members == 2
        assert sorted(events[0].member_ids) == [69, 70]

    def test_different_source_id_and_case_no_same_court_merges(self) -> None:
        """真实 2026-09-09：4 条、2 个 source_id、2 个案号，其实是 1 个庭。"""
        court = "佛山市高明区人民法院 杨和法庭第一审判庭"
        events = normalize(
            make_reminder(
                71,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与A幕墙公司,王铁鑫房屋租赁合同纠纷一案",
                case_id=1,
                case_name="甲诉A幕墙公司、王铁鑫租赁合同纠纷",
                metadata={"courtroom": court, "time_range": "14:30-15:00", "lawyer_name": "黄崧", "source_id": "srcA"},
            ),
            make_reminder(
                72,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与王铁鑫房屋租赁合同纠纷一案",
                case_id=1,
                case_name="甲诉王铁鑫租赁合同纠纷",
                metadata={
                    "courtroom": court,
                    "time_range": "14:30-15:00",
                    "lawyer_name": "房长波",
                    "source_id": "srcB",
                },
            ),
            make_reminder(
                73,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与王铁鑫房屋租赁合同纠纷一案",
                case_id=1,
                case_name="甲诉王铁鑫租赁合同纠纷",
                metadata={"courtroom": court, "time_range": "14:30-15:00", "lawyer_name": "黄崧", "source_id": "srcB"},
            ),
            make_reminder(
                74,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与A幕墙公司,王铁鑫房屋租赁合同纠纷一案",
                case_id=1,
                case_name="甲诉A幕墙公司、王铁鑫租赁合同纠纷",
                metadata={
                    "courtroom": court,
                    "time_range": "14:30-15:00",
                    "lawyer_name": "房长波",
                    "source_id": "srcA",
                },
            ),
        )
        assert len(events) == 1
        assert events[0].members == 4
        # 律师去重且按出现顺序
        assert events[0].person == "黄崧、房长波"

    def test_hearing_without_courtroom_not_merged(self) -> None:
        """手工庭没有法庭信息 → 不合并，否则同时刻的不同案子会被并成一条。"""
        events = normalize(
            make_reminder(1, due_at="2026-09-24T09:00:00+08:00", content="开庭 A 案"),
            make_reminder(2, due_at="2026-09-24T09:00:00+08:00", content="开庭 B 案"),
        )
        assert len(events) == 2

    def test_same_court_different_day_not_merged(self) -> None:
        """改期的同一个庭不能合并成一条。"""
        events = normalize(
            make_reminder(
                1,
                due_at="2026-09-09T06:30:00+00:00",
                content="某庭",
                metadata={"courtroom": "A 法庭", "time_range": "14:30-15:00"},
            ),
            make_reminder(
                2,
                due_at="2026-09-10T06:30:00+00:00",
                content="某庭",
                metadata={"courtroom": "A 法庭", "time_range": "14:30-15:00"},
            ),
        )
        assert len(events) == 2

    def test_non_hearing_never_merged(self) -> None:
        """期限/日程即使字段全相同也不合并。"""
        events = normalize(
            make_reminder(1, due_at="2026-09-22T23:59:00+08:00", reminder_type="evidence_deadline", content="举证截止"),
            make_reminder(2, due_at="2026-09-22T23:59:00+08:00", reminder_type="evidence_deadline", content="举证截止"),
        )
        assert len(events) == 2

    def test_merged_fills_missing_title_from_later_record(self) -> None:
        """首条 content 潦草时，用后续记录的案名补上。"""
        events = normalize(
            make_reminder(
                1,
                due_at="2026-09-24T09:50:00+08:00",
                content="明天开庭",
                metadata={"courtroom": "A 法庭", "time_range": "09:50-10:30"},
            ),
            make_reminder(
                2,
                due_at="2026-09-24T09:50:00+08:00",
                content="明天开庭",
                case_id=377,
                case_name="兴业银行诉升平公司金融借款纠纷一案",
                metadata={"courtroom": "A 法庭", "time_range": "09:50-10:30"},
            ),
        )
        assert len(events) == 1
        assert events[0].title == "兴业银行诉升平公司金融借款纠纷一案"
        assert events[0].case_id == 377


class TestGrouping:
    def test_group_by_day_keys_are_date_strings(self) -> None:
        events = normalize(
            make_reminder(1, due_at="2026-09-21T09:30:00+08:00", content="A"),
            make_reminder(2, due_at="2026-09-21T14:30:00+08:00", content="B"),
            make_reminder(3, due_at="2026-09-22T10:00:00+08:00", content="C"),
        )
        grouped = group_by_day(events)
        assert set(grouped.keys()) == {"2026-09-21", "2026-09-22"}
        assert len(grouped["2026-09-21"]) == 2

    def test_key_kinds_sort_first_within_day(self) -> None:
        events = normalize(
            make_reminder(1, due_at="2026-09-24T16:30:00+08:00", reminder_type="other", content="常规晚"),
            make_reminder(2, due_at="2026-09-24T23:59:00+08:00", reminder_type="appeal_deadline", content="期限晚"),
            make_reminder(3, due_at="2026-09-24T10:00:00+08:00", reminder_type="hearing", content="开庭早"),
        )
        grouped = group_by_day(events)
        kinds = [e.kind for e in grouped["2026-09-24"]]
        assert kinds[0] == EventKind.COURT
        assert kinds[1] == EventKind.DEADLINE
        assert kinds[2] == EventKind.MEETING


class TestStats:
    def test_month_court_counts_merged_hearings(self) -> None:
        """统计必须按合并后口径——否则同一庭会被数成 2 个。"""
        events = normalize(
            make_reminder(
                1,
                due_at="2026-09-01T07:30:00+00:00",
                metadata={"courtroom": "A 法庭", "time_range": "15:30-16:00", "lawyer_name": "甲"},
            ),
            make_reminder(
                2,
                due_at="2026-09-01T07:30:00+00:00",
                metadata={"courtroom": "A 法庭", "time_range": "15:30-16:00", "lawyer_name": "乙"},
            ),
            make_reminder(
                3, due_at="2026-09-24T09:50:00+08:00", metadata={"courtroom": "B 法庭", "time_range": "09:50-10:30"}
            ),
        )
        stats = compute_stats(events, today=date(2026, 9, 26))
        assert stats.month_court == 2  # 不是 3

    def test_deadline_in_7days_window_and_kinds(self) -> None:
        events = normalize(
            make_reminder(1, due_at="2026-09-26T23:59:00+08:00", reminder_type="evidence_deadline", content="今天期限"),
            make_reminder(2, due_at="2026-09-26T09:30:00+08:00", reminder_type="hearing", content="今天开庭"),
            make_reminder(3, due_at="2026-09-30T09:30:00+08:00", reminder_type="hearing", content="4天后"),
            make_reminder(4, due_at="2026-10-05T09:30:00+08:00", reminder_type="hearing", content="超窗"),
            make_reminder(5, due_at="2026-09-27T10:00:00+08:00", reminder_type="other", content="常规不计"),
        )
        stats = compute_stats(events, today=date(2026, 9, 26))
        # 今天 2 个紧要 + 9/30 1 个 = 3；10/05 超窗、9/27 是常规
        assert stats.deadline_in_7days == 3
        assert stats.today == 2

    def test_month_court_ignores_other_months(self) -> None:
        events = normalize(
            make_reminder(1, due_at="2026-09-24T09:50:00+08:00", metadata={"courtroom": "A"}),
            make_reminder(2, due_at="2026-10-15T09:00:00+08:00", metadata={"courtroom": "B"}),
        )
        stats = compute_stats(events, today=date(2026, 9, 26))
        assert stats.month_court == 1

    def test_empty_input(self) -> None:
        stats = compute_stats([], today=date(2026, 9, 26))
        assert (stats.today, stats.deadline_in_7days, stats.month_court) == (0, 0, 0)


class TestRealWorldSeptember:
    def test_september_sept_has_three_hearings(self) -> None:
        """回归：9 月 7 条原始 hearing 应为 3 个庭（真实数据形态）。"""
        court_a = "东莞市第一人民法院 寮步第三审判庭"
        court_b = "佛山市高明区人民法院 杨和法庭第一审判庭"
        raw = [
            make_reminder(
                69,
                due_at="2026-09-01T07:30:00+00:00",
                case_id=351,
                case_name="志承诉威盛买卖合同纠纷一案",
                metadata={
                    "courtroom": court_a,
                    "time_range": "15:30-16:00",
                    "lawyer_name": "房长波",
                    "source_id": "s1",
                },
            ),
            make_reminder(
                70,
                due_at="2026-09-01T07:30:00+00:00",
                case_id=351,
                case_name="志承诉威盛买卖合同纠纷一案",
                metadata={"courtroom": court_a, "time_range": "15:30-16:00", "lawyer_name": "黄崧", "source_id": "s1"},
            ),
            make_reminder(
                71,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与A,王铁鑫租赁纠纷",
                case_id=1,
                case_name="甲诉A、王铁鑫租赁纠纷",
                metadata={"courtroom": court_b, "time_range": "14:30-15:00", "lawyer_name": "黄崧", "source_id": "s2"},
            ),
            make_reminder(
                72,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与王铁鑫租赁纠纷",
                case_id=1,
                case_name="甲诉王铁鑫租赁纠纷",
                metadata={
                    "courtroom": court_b,
                    "time_range": "14:30-15:00",
                    "lawyer_name": "房长波",
                    "source_id": "s3",
                },
            ),
            make_reminder(
                73,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与王铁鑫租赁纠纷",
                case_id=1,
                case_name="甲诉王铁鑫租赁纠纷",
                metadata={"courtroom": court_b, "time_range": "14:30-15:00", "lawyer_name": "黄崧", "source_id": "s3"},
            ),
            make_reminder(
                74,
                due_at="2026-09-09T06:30:00+00:00",
                content="甲与A,王铁鑫租赁纠纷",
                case_id=1,
                case_name="甲诉A、王铁鑫租赁纠纷",
                metadata={
                    "courtroom": court_b,
                    "time_range": "14:30-15:00",
                    "lawyer_name": "房长波",
                    "source_id": "s2",
                },
            ),
            # 手工庭：无 metadata，不合并
            make_reminder(
                75,
                due_at="2026-09-24T01:50:00+00:00",
                content="代理升平百货被告开庭",
                case_id=377,
                case_name="兴业银行诉升平公司、陈达明金融借款纠纷一案",
            ),
        ]
        events = normalize(*raw)
        grouped = group_by_day(events)
        assert set(grouped.keys()) == {"2026-09-01", "2026-09-09", "2026-09-24"}
        assert len(events) == 3
        assert grouped["2026-09-01"][0].members == 2
        assert grouped["2026-09-09"][0].members == 4
        assert grouped["2026-09-24"][0].members == 1
        assert compute_stats(events, today=date(2026, 9, 26)).month_court == 3


class TestFieldExtraction:
    def test_metadata_fields_mapped(self) -> None:
        events = normalize(
            make_reminder(
                1,
                due_at="2026-10-16T10:00:00+08:00",
                case_id=351,
                case_name="某买卖合同案",
                metadata={
                    "courtroom": "佛山禅城中央法务区第三审判庭",
                    "time_range": "10:00-12:00",
                    "lawyer_name": "房长波",
                    "ajbs": "259820260301031696",
                    "hearing_type": "线下开庭",
                },
            ),
        )
        e = events[0]
        assert e.place == "佛山禅城中央法务区第三审判庭"
        assert e.time_range == "10:00-12:00"
        assert e.person == "房长波"
        assert e.case_no == "259820260301031696"
        assert e.hearing_type == "线下开庭"
        assert e.day == "2026-10-16"
        assert e.time == "10:00"

    def test_location_used_when_no_courtroom(self) -> None:
        events = normalize(
            make_reminder(
                1,
                due_at="2026-10-16T10:00:00+08:00",
                metadata={"location": "腾讯会议 123-456-789"},
            ),
        )
        assert events[0].place == "腾讯会议 123-456-789"

    def test_is_overdue_flag(self) -> None:
        events = normalize(
            make_reminder(1, due_at="2026-09-01T02:00:00+00:00", content="过去的庭"),
            make_reminder(2, due_at="2026-10-01T02:00:00+00:00", content="未来的庭"),
        )
        by_id = {e.id: e for e in events}
        assert by_id[1].is_overdue is True
        assert by_id[2].is_overdue is False
