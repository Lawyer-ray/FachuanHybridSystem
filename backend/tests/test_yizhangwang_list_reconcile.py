"""一张网案件列表（ajlist）导入 / 对账的单元测试。

全部用 mock 替换 HTTP 与登录，不依赖真实一张网接口：
- `acquire_zxfw_token` → 返回固定 token
- `fetch_all_cases` → 返回构造好的 `YizhangwangCaseSummary`

覆盖点：
1. 列表项归一化（c 前缀字段、时间戳/字符串时间、缺失 ajbh）
2. 对账三分类（可导入 / 一致 / 有差异）
3. 导入幂等（重复导入不产生重复案件）
4. 案件名称「诉/与」同义措辞不报差异
5. 已结案案件默认不导入
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import patch

import pytest

from plugins.court_automation.case_sync.list_client import (
    YizhangwangCaseSummary,
    _parse_date_value,
    _parse_epoch_ms,
    _to_summary,
)
from plugins.court_automation.case_sync.reconcile import reconcile_cases

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# 列表项归一化
# ---------------------------------------------------------------------------


def test_to_summary_parses_c_prefixed_fields() -> None:
    """列表接口字段带 c 前缀，归一化后要落到 dataclass 对应字段上。"""
    item = {
        "cajbh": "ajbh-1",
        "cbh": "pkg-1",
        "cah": "（20XX）粤01民初某某号",
        "cajmc": "张某诉某公司买卖合同纠纷一案",
        "claay": "买卖合同纠纷",
        "cfydmTranslateText": "佛山市禅城区人民法院",
        "ccbsptTranslateText": "民事审判庭",
        "ccbrTranslateText": "张三",
        "cajjzjdTranslateText": "正在审理",
        "cajlb": "1501_000001-0300",
        "cywlxTranslateText": "民事一审案件",
        "cysah": "（20XX）粤01民初某某号",
        "cysfyTranslateText": "佛山市禅城区人民法院",
        "cktsj": "2026-11-24 09:00:00",
        "clarq": "2026-09-09",
    }

    summary = _to_summary(item)

    assert summary is not None
    assert summary.ajbh == "ajbh-1"
    assert summary.package_bh == "pkg-1"
    assert summary.case_number == "（20XX）粤01民初某某号"
    assert summary.cause_of_action == "买卖合同纠纷"
    assert summary.court_name == "佛山市禅城区人民法院"
    assert summary.judge == "张三"
    assert summary.stage == "正在审理"
    assert summary.category_label == "民事"
    assert summary.first_instance_number == "（20XX）粤01民初某某号"
    assert summary.hearing_at == datetime.fromisoformat("2026-11-24 09:00:00").replace(tzinfo=summary.hearing_at.tzinfo)
    assert summary.filed_on == date(2026, 9, 9)
    assert summary.is_missing_number is False


def test_to_summary_drops_record_without_ajbh() -> None:
    """没有 ajbh 的记录无法与本地对账，必须丢弃。"""
    assert _to_summary({"cah": "（20XX）粤01民初某某号"}) is None
    assert _to_summary("not-a-dict") is None  # type: ignore[arg-type]


def test_parse_epoch_ms_handles_timestamp_and_string_forms() -> None:
    """详情接口给毫秒时间戳，列表接口给字符串，解析器两者都要吃。"""
    # 毫秒时间戳（详情接口 ajVO.ktsj）
    parsed = _parse_epoch_ms(1794274200000)
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute) == (2026, 11, 10, 9, 30)

    # 带时区 ISO 串（列表接口 d 前缀，UTC）
    iso = _parse_epoch_ms("2026-11-10T01:30:00.000+00:00")
    assert iso is not None
    assert (iso.hour, iso.minute) == (9, 30)

    # 本地时间串（列表接口 c 前缀）
    local = _parse_epoch_ms("2026-11-10 09:30:00")
    assert local is not None
    assert (local.hour, local.minute) == (9, 30)

    # 非法值
    for bad in (0, None, "", "abc", -1):
        assert _parse_epoch_ms(bad) is None


def test_parse_date_value_returns_local_date() -> None:
    assert _parse_date_value("2026-09-09") == date(2026, 9, 9)
    assert _parse_date_value(None) is None


# ---------------------------------------------------------------------------
# 对账
# ---------------------------------------------------------------------------


def _summary(ajbh: str, **overrides: Any) -> YizhangwangCaseSummary:
    base: dict[str, Any] = {
        "ajbh": ajbh,
        "case_number": "（20XX）粤01民初某某号",
        "case_name": "张某诉某公司买卖合同纠纷一案",
        "cause_of_action": "买卖合同纠纷",
        "court_name": "佛山市禅城区人民法院",
        "stage": "正在审理",
        "category_label": "民事",
        "filed_on": date(2026, 9, 9),
    }
    base.update(overrides)
    return YizhangwangCaseSummary(**base)


@pytest.fixture
def lawyer(db: Any) -> Any:
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create(username="yz_test_lawyer", real_name="测试律师")


def _run_reconcile(lawyer: Any, summaries: list[YizhangwangCaseSummary], mode: str = "reconcile") -> Any:
    """在 mock 掉登录与列表拉取的前提下跑对账。"""
    credential = {"id": "1", "account": "test", "password": "test"}  # pragma: allowlist secret
    with (
        patch(
            "plugins.court_automation.case_sync.client.resolve_lawyer_credential",
            return_value=credential,
        ),
        patch(
            "plugins.court_automation.case_sync.client.acquire_zxfw_token",
            return_value="token",
        ),
        patch(
            "plugins.court_automation.case_sync.list_client.fetch_all_cases",
            return_value=summaries,
        ),
    ):
        return reconcile_cases(lawyer, mode=mode)


def test_reconcile_classifies_new_matching_and_diff(lawyer: Any) -> None:
    """远程有 3 条：1 条本地没有、1 条完全一致、1 条案由有差异。"""
    from apps.cases.models import Case, CaseNumber

    # 本地已有：完全一致
    clean = Case.objects.create(yz_wid="aj-clean", name="张某诉某公司买卖合同纠纷一案", cause_of_action="买卖合同纠纷")
    CaseNumber.objects.create(case=clean, number="（20XX）粤01民初某某号")

    # 本地已有：案由不一致
    dirty = Case.objects.create(yz_wid="aj-dirty", name="李某诉某厂买卖合同纠纷一案", cause_of_action="旧案由")
    CaseNumber.objects.create(case=dirty, number="（20XX）粤01民初某某号")

    summaries = [
        _summary("aj-new", case_number="（20XX）粤01民初某某号", case_name="王某诉某中心买卖合同纠纷一案"),
        _summary("aj-clean"),
        _summary("aj-dirty", case_name="李某诉某厂买卖合同纠纷一案", cause_of_action="新案由"),
    ]

    result = _run_reconcile(lawyer, summaries)

    assert [s.ajbh for s in result.missing_local] == ["aj-new"]
    assert [m.case.pk for m in result.matched_clean] == [clean.pk]
    assert [m.case.pk for m in result.matched_dirty] == [dirty.pk]
    assert "案由" in result.matched_dirty[0].diffs
    assert result.created == []


def test_reconcile_ignores_su_vs_yu_wording(lawyer: Any) -> None:
    """本地「甲诉乙」与一张网「甲与乙」指向同一案件，不应报差异。"""
    from apps.cases.models import Case, CaseNumber

    case = Case.objects.create(yz_wid="aj-1", name="张某诉某公司买卖合同纠纷一案", cause_of_action="买卖合同纠纷")
    CaseNumber.objects.create(case=case, number="（20XX）粤01民初某某号")

    summaries = [_summary("aj-1", case_name="张某与某公司买卖合同纠纷一案")]

    result = _run_reconcile(lawyer, summaries)

    assert result.matched_dirty == []
    assert len(result.matched_clean) == 1


def test_reconcile_skips_closed_cases_by_default(lawyer: Any) -> None:
    """一张网已结案的案件默认不进「可导入」，除非显式 include_closed。"""
    closed = _summary("aj-closed", case_number="（20XX）粤01民初某某号", stage="已结案")

    result = _run_reconcile(lawyer, [closed])
    assert result.missing_local == []

    credential = {"id": "1", "account": "test", "password": "test"}  # pragma: allowlist secret
    with (
        patch(
            "plugins.court_automation.case_sync.client.resolve_lawyer_credential",
            return_value=credential,
        ),
        patch(
            "plugins.court_automation.case_sync.client.acquire_zxfw_token",
            return_value="token",
        ),
        patch(
            "plugins.court_automation.case_sync.list_client.fetch_all_cases",
            return_value=[closed],
        ),
    ):
        result2 = reconcile_cases(lawyer, mode="reconcile", include_closed=True)
    assert [s.ajbh for s in result2.missing_local] == ["aj-closed"]


def test_import_creates_case_and_is_idempotent(lawyer: Any) -> None:
    """导入要建出 Case + 案号 + 指派，且重复导入不产生重复数据。"""
    from apps.cases.models import Case, CaseNumber

    summaries = [
        _summary("aj-import", case_number="（20XX）粤01民初某某号", case_name="赵某诉某商场买卖合同纠纷一案"),
    ]

    result = _run_reconcile(lawyer, summaries, mode="import")
    assert len(result.created) == 1

    created = result.created[0]
    assert created.yz_wid == "aj-import"
    assert created.start_date == date(2026, 9, 9)
    assert created.case_type == "civil"
    assert CaseNumber.objects.filter(case=created, number="（20XX）粤01民初某某号").exists()
    assert created.assignments.filter(lawyer=lawyer).exists()

    before = Case.objects.count()

    # 第二次导入：同一 ajbh 已在本地，不应再建新案件
    result2 = _run_reconcile(lawyer, summaries, mode="import")
    assert result2.created == []
    assert Case.objects.count() == before
    assert len(result2.matched_clean) + len(result2.matched_dirty) == 1


def test_import_fills_only_blank_fields(lawyer: Any) -> None:
    """导入模式下，本地已填的字段不被覆盖，只有空字段被补全。"""
    from apps.cases.models import Case, CaseNumber

    case = Case.objects.create(yz_wid="aj-fill", name="", cause_of_action="本地已填案由")
    CaseNumber.objects.create(case=case, number="（20XX）粤01民初某某号")

    summaries = [
        _summary("aj-fill", case_name="孙某诉某商行买卖合同纠纷一案", cause_of_action="一张网案由"),
    ]

    _run_reconcile(lawyer, summaries, mode="import")

    case.refresh_from_db()
    assert case.name == "孙某诉某商行买卖合同纠纷一案"  # 空 → 补全
    assert case.cause_of_action == "本地已填案由"  # 非空 → 不覆盖


def test_reconcile_rejects_unknown_mode(lawyer: Any) -> None:
    with pytest.raises(ValueError):
        reconcile_cases(lawyer, mode="bogus")
