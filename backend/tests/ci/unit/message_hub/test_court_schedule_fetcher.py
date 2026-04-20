"""CourtScheduleFetcher 单元测试 — 分词、案件关联、upsert 全链路。"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.utils import timezone

from apps.message_hub.models import MessageSource, SourceType, SyncStatus
from apps.message_hub.services.court.court_schedule_fetcher import (
    CourtScheduleFetcher,
    ParsedHearing,
    _extract_party_names,
    _find_case_id,
    _is_valid_party_name,
    _match_by_case_number,
    _match_by_party_names,
    _parse_datetime,
)
from apps.reminders.models import Reminder, ReminderType

# ---------------------------------------------------------------------------
# _parse_datetime 测试
# ---------------------------------------------------------------------------


class TestParseDatetime:
    """时间字符串解析测试。"""

    def test_normal_format(self):
        dt = _parse_datetime("2026-05-29 16:30")
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 29
        assert dt.hour == 16
        assert dt.minute == 30
        assert timezone.is_aware(dt)

    def test_with_seconds(self):
        dt = _parse_datetime("2026-05-29 16:30:00")
        # 格式不含秒，回退到 now
        assert dt is not None

    def test_empty_string(self):
        dt = _parse_datetime("")
        assert dt is not None  # 回退到 now

    def test_none_input(self):
        dt = _parse_datetime(None)  # type: ignore[arg-type]
        assert dt is not None


# ---------------------------------------------------------------------------
# _extract_party_names 分词测试
# ---------------------------------------------------------------------------


class TestExtractPartyNames:
    """rcbt 日程标题分词测试。"""

    def test_simple_two_party(self):
        """简单两方：原告与被告。"""
        names = _extract_party_names("广东志承电器有限公司与汪达买卖合同纠纷一案")
        assert "广东志承电器有限公司" in names
        assert "汪达" in names

    def test_multiple_defendants(self):
        """多个被告：逗号分隔。"""
        names = _extract_party_names("梁毅鹏与郑建云,曾强民间借贷纠纷一案")
        assert "梁毅鹏" in names
        assert "郑建云" in names
        assert "曾强" in names

    def test_company_multiple_defendants(self):
        """公司+多被告+案由噪声。"""
        names = _extract_party_names(
            "佛山市升平百货有限公司与佛山市仲满金属材料有限公司,郑汝钋,石莹追偿权纠纷一案"
        )
        assert "佛山市升平百货有限公司" in names
        assert "佛山市仲满金属材料有限公司" in names
        assert "郑汝钋" in names
        # "石莹追偿权纠纷" 应被过滤（案由噪声）
        assert "石莹追偿权纠纷" not in names

    def test_complex_administrative(self):
        """行政案件：含括号和复杂当事人。"""
        names = _extract_party_names(
            "海南南海翔龙实业有限公司与国家税务总局海南省税务局第二稽查局,国家税务总局海南省税务局××（行政行为）及行政复议一案"
        )
        assert "海南南海翔龙实业有限公司" in names
        assert "国家税务总局海南省税务局第二稽查局" in names

    def test_empty_string(self):
        names = _extract_party_names("")
        assert names == []

    def test_no_yu_character(self):
        """无「与」分隔时返回空。"""
        names = _extract_party_names("追偿权纠纷")
        assert names == []

    def test_fullwidth_comma(self):
        """全角逗号分隔。"""
        names = _extract_party_names("张三与李四，王五买卖合同纠纷一案")
        assert "张三" in names
        assert "李四" in names
        assert "王五" in names


# ---------------------------------------------------------------------------
# _is_valid_party_name 测试
# ---------------------------------------------------------------------------


class TestIsValidPartyName:
    """当事人名称有效性过滤测试。"""

    def test_company_name(self):
        assert _is_valid_party_name("佛山市升平百货有限公司") is True

    def test_person_name_short(self):
        assert _is_valid_party_name("郑汝钋") is True

    def test_case_cause_noise(self):
        assert _is_valid_party_name("追偿权纠纷") is False

    def test_short_case_cause(self):
        assert _is_valid_party_name("纠纷") is False

    def test_empty(self):
        assert _is_valid_party_name("") is False

    def test_single_char(self):
        assert _is_valid_party_name("李") is False

    def test_government_bureau(self):
        assert _is_valid_party_name("国家税务总局海南省税务局第二稽查局") is True


# ---------------------------------------------------------------------------
# 案件关联策略测试
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFindCaseId:
    """案件关联二级匹配测试。"""

    def test_s1_exact_match_by_case_number(self):
        """S1: 正式案号精确匹配。"""
        from apps.cases.models import Case, CaseNumber
        from apps.cases.models.party import CaseParty
        from apps.client.models import Client

        client = Client.objects.create(name="测试当事人")
        case = Case.objects.create(name="测试案件")
        CaseNumber.objects.create(case=case, number="（2025）粤0604民初48857号")
        CaseParty.objects.create(case=case, client=client)

        record = {"ah": "（2025）粤0604民初48857号", "rcbt": "测试案件"}
        case_id, strategy = _find_case_id(record)
        assert case_id == case.id
        assert strategy == "exact"

    def test_s2_party_match(self):
        """S2: 当事人名称匹配。"""
        from apps.cases.models import Case
        from apps.cases.models.party import CaseParty
        from apps.client.models import Client

        client1 = Client.objects.create(name="佛山市升平百货有限公司")
        client2 = Client.objects.create(name="佛山市仲满金属材料有限公司")
        case = Case.objects.create(name="升平百货案件")
        CaseParty.objects.create(case=case, client=client1)
        CaseParty.objects.create(case=case, client=client2)

        record = {
            "ah": None,
            "rcbt": "佛山市升平百货有限公司与佛山市仲满金属材料有限公司,郑汝钋追偿权纠纷一案",
        }
        case_id, strategy = _find_case_id(record)
        assert case_id == case.id
        assert strategy == "party"

    def test_s2_no_match_returns_none(self):
        """S2: 当事人无法匹配时返回 None。"""
        record = {"ah": None, "rcbt": "不存在的公司与另一家公司合同纠纷一案"}
        case_id, strategy = _find_case_id(record)
        assert case_id is None
        assert strategy == "none"

    def test_s2_multiple_cases_intersection_returns_none(self):
        """S2: 多当事人命中的案件交集为空或>1时不绑定。"""
        from apps.cases.models import Case
        from apps.cases.models.party import CaseParty
        from apps.client.models import Client

        client1 = Client.objects.create(name="甲方有限公司")
        client2 = Client.objects.create(name="乙方有限公司")
        # 两个案件各只有一个当事人 — 交集为空（不在同一个案件）
        case1 = Case.objects.create(name="案件1")
        case2 = Case.objects.create(name="案件2")
        CaseParty.objects.create(case=case1, client=client1)
        CaseParty.objects.create(case=case2, client=client2)

        # rcbt 中甲方和乙方不在同一个案件 → 交集为空
        record = {"ah": None, "rcbt": "甲方有限公司与乙方有限公司合同纠纷一案"}
        case_id, strategy = _find_case_id(record)
        assert case_id is None
        assert strategy == "none"

    def test_s3_no_ah_no_rcbt(self):
        """S3: 无案号无标题，不关联。"""
        record = {"ah": None, "rcbt": ""}
        case_id, strategy = _find_case_id(record)
        assert case_id is None
        assert strategy == "none"


# ---------------------------------------------------------------------------
# CourtScheduleFetcher 完整流程测试
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCourtScheduleFetcher:
    """CourtScheduleFetcher 端到端测试。"""

    def setup_method(self):
        from apps.organization.models import AccountCredential, Lawyer

        # Lawyer 需要 law_firm，使用 get_or_create 避免冲突
        lawyer, _ = Lawyer.objects.get_or_create(
            username="test_schedule_lawyer",
            defaults={"real_name": "测试律师"},
        )
        self.credential = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="court_zxfw",
            account="test_account",
            password="placeholder",
            url="https://zxfw.court.gov.cn",
        )
        self.source = MessageSource.objects.create(
            credential=self.credential,
            source_type=SourceType.COURT_SCHEDULE,
            display_name="测试庭审日程",
            is_enabled=True,
            poll_interval_minutes=30,
            sync_since=timezone.now() - timedelta(days=365),
        )
        self.fetcher = CourtScheduleFetcher()

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_empty_data(self, mock_token, mock_api):
        """空数据返回 0。"""
        mock_token.return_value = "fake_token"
        mock_api.return_value = {"data": [], "totalRows": 0}

        count = self.fetcher.fetch_new_messages(self.source)
        assert count == 0
        self.source.refresh_from_db()
        assert self.source.last_sync_status == SyncStatus.SUCCESS

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_creates_reminders(self, mock_token, mock_api):
        """正常数据创建 Reminder。"""
        mock_token.return_value = "fake_token"
        mock_api.return_value = {
            "data": [
                {
                    "bh": "unique-id-001",
                    "ajbs": "260220250301096742",
                    "ah": None,
                    "kssj": "2026-06-15 09:30",
                    "jssj": "2026-06-15 10:30",
                    "sj": "09:30-10:30",
                    "rcbt": "测试公司与另一公司合同纠纷一案",
                    "rcdd": "佛山市顺德区人民法院 第一审判庭",
                    "lx": "线下开庭",
                    "fydm": "2602",
                    "cjfs": 0,
                    "hasCase": True,
                    "najzt": 1,
                }
            ],
            "totalRows": 1,
        }

        count = self.fetcher.fetch_new_messages(self.source)
        assert count == 1
        assert Reminder.objects.filter(reminder_type=ReminderType.HEARING, metadata__source_id="unique-id-001").count() == 1

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_dedup_same_bh(self, mock_token, mock_api):
        """相同 bh 去重，不重复创建。"""
        mock_token.return_value = "fake_token"
        mock_api.return_value = {
            "data": [
                {
                    "bh": "dup-id-001",
                    "ajbs": "123",
                    "ah": None,
                    "kssj": "2026-06-15 09:30",
                    "jssj": "2026-06-15 10:30",
                    "sj": "09:30-10:30",
                    "rcbt": "测试案件一案",
                    "rcdd": "法院",
                    "lx": "线下开庭",
                    "fydm": "2602",
                    "cjfs": 0,
                    "hasCase": False,
                    "najzt": 1,
                }
            ],
            "totalRows": 1,
        }

        # 第一次
        count1 = self.fetcher.fetch_new_messages(self.source)
        assert count1 == 1

        reminder = Reminder.objects.get(metadata__source_id="dup-id-001")
        first_updated_at = reminder.updated_at

        # 第二次 — 同一 bh 且数据无变化，应跳过更新
        count2 = self.fetcher.fetch_new_messages(self.source)
        assert count2 == 0
        reminder_after = Reminder.objects.get(metadata__source_id="dup-id-001")
        assert reminder_after.updated_at == first_updated_at
        assert Reminder.objects.filter(metadata__source_id="dup-id-001").count() == 1

        reminder.refresh_from_db()
        assert reminder.updated_at == first_updated_at

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_skips_no_time_record(self, mock_token, mock_api):
        """无 kssj 的记录跳过。"""
        mock_token.return_value = "fake_token"
        mock_api.return_value = {
            "data": [
                {
                    "bh": "no-time-id",
                    "ajbs": "123",
                    "ah": None,
                    "kssj": "",
                    "jssj": "",
                    "sj": "",
                    "rcbt": "无时间案件一案",
                    "rcdd": "",
                    "lx": "",
                    "fydm": "",
                    "cjfs": 0,
                    "hasCase": False,
                    "najzt": 1,
                }
            ],
            "totalRows": 1,
        }

        count = self.fetcher.fetch_new_messages(self.source)
        assert count == 0

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_pagination(self, mock_token, mock_api):
        """多页数据完整拉取。"""
        mock_token.return_value = "fake_token"

        page1_data = [
            {"bh": f"page1-{i}", "ajbs": str(i), "ah": None, "kssj": "2026-06-15 09:30", "jssj": "2026-06-15 10:30", "sj": "09:30-10:30", "rcbt": f"案件{i}一案", "rcdd": "法院", "lx": "线下开庭", "fydm": "2602", "cjfs": 0, "hasCase": False, "najzt": 1}
            for i in range(20)
        ]
        page2_data = [
            {"bh": f"page2-{i}", "ajbs": str(i + 20), "ah": None, "kssj": "2026-06-16 09:30", "jssj": "2026-06-16 10:30", "sj": "09:30-10:30", "rcbt": f"案件{i+20}一案", "rcdd": "法院", "lx": "线下开庭", "fydm": "2602", "cjfs": 0, "hasCase": False, "najzt": 1}
            for i in range(5)
        ]

        def api_side_effect(url, token, data):
            if data.get("pageNo") == 1:
                return {"data": page1_data, "totalRows": 25}
            return {"data": page2_data, "totalRows": 25}

        mock_api.side_effect = api_side_effect

        count = self.fetcher.fetch_new_messages(self.source)
        assert count == 25
        assert mock_api.call_count == 2

    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_token_expired_retry(self, mock_token):
        """Token 过期重试逻辑。"""
        mock_token.return_value = "new_token"

        with patch("apps.message_hub.services.court.court_schedule_fetcher._api_post") as mock_api:
            # 第一次调用抛出 PermissionError（Token 过期）
            mock_api.side_effect = [PermissionError("Token expired"), {"data": [], "totalRows": 0}]

            with patch("apps.message_hub.services.court.court_schedule_fetcher._invalidate_token"):
                count = self.fetcher.fetch_new_messages(self.source)

        assert count == 0
        assert mock_token.call_count == 2  # 初始 + 重试

    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_server_error_retry_with_token_refresh(self, mock_token):
        """5xx 场景应刷新 Token 并重试一次。"""
        mock_token.side_effect = ["old_token", "new_token"]

        request = httpx.Request("POST", "https://zxfw.court.gov.cn/yzw/yzw-zxfw-xxfw/api/v1/zhrl/list")
        response = httpx.Response(500, request=request)
        server_error = httpx.HTTPStatusError("Server error", request=request, response=response)

        with patch("apps.message_hub.services.court.court_schedule_fetcher._api_post") as mock_api:
            mock_api.side_effect = [server_error, {"data": [], "totalRows": 0}]

            with patch("apps.message_hub.services.court.court_schedule_fetcher._invalidate_token") as mock_invalidate:
                count = self.fetcher.fetch_new_messages(self.source)

        assert count == 0
        assert mock_token.call_count == 2
        mock_invalidate.assert_called_once()

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_fetch_marks_failed_on_token_error(self, mock_token, mock_api):
        """Token 获取失败标记同步失败。"""
        mock_token.side_effect = RuntimeError("凭证不存在")

        with pytest.raises(RuntimeError, match="凭证不存在"):
            self.fetcher.fetch_new_messages(self.source)

        self.source.refresh_from_db()
        assert self.source.last_sync_status == SyncStatus.FAILED

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_metadata_contains_match_strategy(self, mock_token, mock_api):
        """metadata 包含 match_strategy 字段。"""
        mock_token.return_value = "fake_token"
        mock_api.return_value = {
            "data": [
                {
                    "bh": "strategy-test-id",
                    "ajbs": "123",
                    "ah": None,
                    "kssj": "2026-06-15 09:30",
                    "jssj": "2026-06-15 10:30",
                    "sj": "09:30-10:30",
                    "rcbt": "不存在的公司合同纠纷一案",
                    "rcdd": "法院",
                    "lx": "线下开庭",
                    "fydm": "2602",
                    "cjfs": 0,
                    "hasCase": False,
                    "najzt": 1,
                }
            ],
            "totalRows": 1,
        }

        self.fetcher.fetch_new_messages(self.source)
        reminder = Reminder.objects.get(metadata__source_id="strategy-test-id")
        assert reminder.metadata["match_strategy"] == "none"
        assert reminder.metadata["source_type"] == "court_schedule"
        assert reminder.metadata["lawyer_name"] == "测试律师"

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_metadata_contains_lawyer_name(self, mock_token, mock_api):
        """metadata 包含律师姓名。"""
        mock_token.return_value = "fake_token"
        mock_api.return_value = {
            "data": [
                {
                    "bh": "lawyer-test-id",
                    "ajbs": "456",
                    "ah": None,
                    "kssj": "2026-07-01 14:00",
                    "jssj": "2026-07-01 15:00",
                    "sj": "14:00-15:00",
                    "rcbt": "测试案件一案",
                    "rcdd": "佛山市顺德区人民法院",
                    "lx": "线下开庭",
                    "fydm": "2602",
                    "cjfs": 0,
                    "hasCase": False,
                    "najzt": 1,
                }
            ],
            "totalRows": 1,
        }

        self.fetcher.fetch_new_messages(self.source)
        reminder = Reminder.objects.get(metadata__source_id="lawyer-test-id")
        assert reminder.metadata["lawyer_name"] == "测试律师"

    @patch("apps.message_hub.services.court.court_schedule_fetcher._api_post")
    @patch("apps.message_hub.services.court.court_schedule_fetcher._acquire_token")
    def test_same_hearing_different_lawyers_creates_separate_reminders(self, mock_token, mock_api):
        """同一庭审、不同律师各自创建独立的 Reminder，不互相覆盖。"""
        from apps.organization.models import AccountCredential, Lawyer

        # 创建第二个律师和凭证
        lawyer2, _ = Lawyer.objects.get_or_create(
            username="test_schedule_lawyer2",
            defaults={"real_name": "律师二"},
        )
        credential2 = AccountCredential.objects.create(
            lawyer=lawyer2,
            site_name="court_zxfw",
            account="test_account2",
            password="placeholder2",
            url="https://zxfw.court.gov.cn",
        )
        source2 = MessageSource.objects.create(
            credential=credential2,
            source_type=SourceType.COURT_SCHEDULE,
            display_name="律师二庭审日程",
            is_enabled=True,
            poll_interval_minutes=30,
            sync_since=timezone.now() - timedelta(days=365),
        )

        mock_token.return_value = "fake_token"
        mock_api.return_value = {
            "data": [
                {
                    "bh": "shared-hearing-id",
                    "ajbs": "789",
                    "ah": None,
                    "kssj": "2026-08-01 09:30",
                    "jssj": "2026-08-01 10:30",
                    "sj": "09:30-10:30",
                    "rcbt": "共享庭审案件一案",
                    "rcdd": "佛山市顺德区人民法院",
                    "lx": "线下开庭",
                    "fydm": "2602",
                    "cjfs": 0,
                    "hasCase": False,
                    "najzt": 1,
                }
            ],
            "totalRows": 1,
        }

        # 律师一同步
        count1 = self.fetcher.fetch_new_messages(self.source)
        assert count1 == 1

        # 律师二同步 — 同一 bh，应创建独立记录
        count2 = self.fetcher.fetch_new_messages(source2)
        assert count2 == 1

        # 应有两条独立记录
        reminders = Reminder.objects.filter(metadata__source_id="shared-hearing-id")
        assert reminders.count() == 2

        # 各自的 lawyer_name 不同
        names = sorted(r.metadata["lawyer_name"] for r in reminders)
        assert names == ["律师二", "测试律师"]

        # 各自的 source_credential_id 不同
        cred_ids = sorted(r.metadata["source_credential_id"] for r in reminders)
        assert len(set(cred_ids)) == 2
