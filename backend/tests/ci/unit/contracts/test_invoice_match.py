"""发票匹配器（S1–S4）单测。

## 数据样本

`PROJECT_CODE` / `BUYER_NAME` / `REMARK` / `TOTAL_AMOUNT` / `INVOICE_DATE` 取自一条
**已验证的真实发票**：项目号 `2025GZM0001`，购买方 `张三`，价税合计 2400.00，  # privacy-allow 虚构样例，非真实项目号
开票日期 2026-11-10，备注栏原文 `2025GZM0001-张某与某公司合同纠纷;`。  # privacy-allow 虚构样例，非真实项目号
真实命中：该备注里的项目号对应唯一一份合同（`law_firm_oa_case_number` 唯一约束）。

**不硬编码真实主键**：合同 id / 收款 id 在每个用例里由 fixture 现建现取，
断言一律对 fixture 返回的 id，换库/换环境都不会假红。

## 三层测法

1. **纯函数**（项目号抽取 / 归一化 / 相似度 / 名称比对 / 打分 / 排序）：直接测，不经 DB。
2. **分支判定**（`choose_payment` 四个分支、`rank_invoice_candidates` 的组装）：
   被测代码原样运行，只把「取收款列表」「取合格项目」这两个查询入口换成假行集——
   避免把逻辑重写一份去测副本。
3. **真实库**（`test_rank_runs_against_real_database`、
   `test_choose_payment_with_no_payment_in_real_table`、
   `test_s1_hits_real_contract_end_to_end`）：跑真实 `eligible_contract_qs()`
   与真实收款查询。端到端那条现建合同/当事人/收款再断言 S1→S4 全链路，
   退出事务即回滚；测试库 schema 陈旧时由 `contract_table_schema_ready`
   探测后 skip 并说明原因——不假红，也不用 `xfail` 静默通过。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest

from apps.contracts.services.payment.invoice_match import (
    CONFIDENCE_AMBIGUOUS,
    CONFIDENCE_AMOUNT_MISMATCH,
    CONFIDENCE_EXACT,
    CONFIDENCE_NO_PAYMENT,
    KIND_CASE_TEXT,
    KIND_PARTY_NAME,
    KIND_PROJECT_CODE,
    MATCHER_VERSION,
    NOTE_AMBIGUOUS,
    NOTE_AMOUNT_MISMATCH,
    NOTE_NO_PAYMENT,
    InvoiceCandidate,
    case_text_similarity,
    choose_payment,
    extract_project_code_candidates,
    names_match,
    normalize_text,
    rank_candidates,
    rank_invoice_candidates,
    score_contract_for_invoice,
)

# ── 真实样本（一条已验证的真实发票） ───────────────────────
PROJECT_CODE = "2025GZM0001"  # privacy-allow 虚构样例，非真实项目号
BUYER_NAME = "张三"
REMARK = "2025GZM0001-张某与某公司合同纠纷;"  # privacy-allow 虚构样例，非真实项目号
TOTAL_AMOUNT = Decimal("2400.00")
INVOICE_DATE = date(2026, 11, 10)
REAL_FILENAME = "dzfp_26442000012915552076_张三（个人）_2025GZM0001-某某律师.pdf"  # privacy-allow 虚构样例，非真实项目号

#: 与备注里案由对应的合同名（真实合同名的脱敏版，结构未改）
REAL_CONTRACT_NAME = "张三与某公司合同纠纷案"


# ── 假对象：让打分/排序逻辑脱离 ORM 直接可测 ────────────────


class _FakeClient:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeParty:
    def __init__(self, name: str, role: str = "PRINCIPAL") -> None:
        self.role = role
        self.client = _FakeClient(name)


class _FakeParties(list[_FakeParty]):
    def all(self) -> list[_FakeParty]:
        return list(self)


class _FakeContract:
    """只带打分需要的字段，模拟 ``Contract``（含预加载好的当事人）。"""

    def __init__(
        self,
        *,
        contract_id: int,
        name: str,
        oa_number: str | None = None,
        principals: list[str] | None = None,
        opposing: list[str] | None = None,
        end_date: date | None = None,
    ) -> None:
        self.id = contract_id
        self.name = name
        self.law_firm_oa_case_number = oa_number
        self.end_date = end_date
        parties = _FakeParties(_FakeParty(n) for n in (principals or []))
        parties.extend(_FakeParty(n, role="OPPOSING") for n in (opposing or []))
        self.contract_parties = parties


# ── S1/S2/S3 信号：项目号抽取（可配置多形态） ────────────────


class TestExtractProjectCodeCandidates:
    """项目号样式不写死一种：主形态 + 备选形态都要抽到。"""

    def test_real_remark_yields_project_code(self) -> None:
        assert extract_project_code_candidates(REMARK) == [PROJECT_CODE]

    def test_real_filename_yields_project_code(self) -> None:
        assert extract_project_code_candidates(REAL_FILENAME) == [PROJECT_CODE]

    def test_alternate_business_letter_shape_hits(self) -> None:
        """备选形态：业务字母 1 位、序号 4 位（`2026GZG0003`）。"""  # privacy-allow 虚构样例，非真实项目号
        assert extract_project_code_candidates("2026GZG0003") == ["2026GZG0003"]  # privacy-allow 虚构样例，非真实项目号

    def test_two_letter_business_shape_hits(self) -> None:
        """备选形态：业务字母 2 位、序号 4 位（`2025GZMB0034`）。"""  # privacy-allow 虚构样例，非真实项目号
        assert extract_project_code_candidates("dzfp_1_某某_2025GZMB0034-张三.pdf") == ["2025GZMB0034"]  # privacy-allow 虚构样例，非真实项目号

    def test_no_project_code_returns_empty(self) -> None:
        assert extract_project_code_candidates("无项目号") == []

    def test_empty_input_does_not_raise(self) -> None:
        assert extract_project_code_candidates("") == []

    def test_strict_shape_is_not_cut_by_fallback_shape(self) -> None:
        """主形态先扫并占位：`2025GZM0001` 不会同时被备选形态切成 `2025GZM034`。"""  # privacy-allow 虚构样例，非真实项目号
        assert extract_project_code_candidates("2025GZM0001") == ["2025GZM0001"]  # privacy-allow 虚构样例，非真实项目号

    def test_multiple_codes_are_all_returned_in_text_order(self) -> None:
        assert extract_project_code_candidates("2025GZM0001 与 2024GZA1234") == ["2025GZM0001", "2024GZA1234"]  # privacy-allow 虚构样例，非真实项目号

    def test_boundaries_reject_embedded_digits(self) -> None:
        """前后紧贴字母数字的不算项目号（否则长号码会被切出一段假项目号）。"""
        assert extract_project_code_candidates("X2025GZM0001X") == []


# ── 纯函数：归一化 / 相似度 / 名称比对 ──────────────────────


class TestNormalizeAndSimilarity:
    def test_normalize_drops_punctuation_and_whitespace(self) -> None:
        assert normalize_text(REMARK) == "2025GZM0001张某与某公司合同纠纷"  # privacy-allow 虚构样例，非真实项目号

    def test_normalize_folds_full_width(self) -> None:
        """全角括号与半角括号归一后相同：发票买方名常写成全角。"""
        assert normalize_text("深圳市（某某）铝业有限公司") == normalize_text("深圳市(某某)铝业有限公司")

    def test_remark_case_text_matches_contract_name(self) -> None:
        """真实样本：备注里的案由 vs 合同名，去掉项目号与分隔噪声后高度相似。"""
        assert case_text_similarity(REMARK, REAL_CONTRACT_NAME) >= 0.6

    def test_unrelated_contract_name_scores_low(self) -> None:
        assert case_text_similarity(REMARK, "某供应链管理有限公司税务处理案") < 0.6

    def test_identical_text_scores_one(self) -> None:
        assert case_text_similarity(REAL_CONTRACT_NAME, REAL_CONTRACT_NAME) == 1.0

    def test_empty_text_scores_zero_not_one(self) -> None:
        """空串之间的相似度没有意义，不能给 1.0（否则空备注会命中所有合同）。"""
        assert case_text_similarity("", REAL_CONTRACT_NAME) == 0.0
        assert case_text_similarity("", "") == 0.0

    def test_short_common_fragment_does_not_match(self) -> None:
        """「合同纠纷」这类两字片段（噪声剔除后为空）不足以构成 S2 证据。"""
        assert case_text_similarity("合同纠纷", REAL_CONTRACT_NAME) < 0.6

    def test_buyer_name_ignores_personal_marker(self) -> None:
        assert names_match("张三（个人）", BUYER_NAME) is True

    def test_company_name_matches_by_containment(self) -> None:
        assert names_match("深圳市某某铝业有限公司", "某某铝业") is True

    def test_single_char_name_is_not_a_containment_hit(self) -> None:
        assert names_match("何", BUYER_NAME) is False

    def test_empty_names_never_match(self) -> None:
        assert names_match("", BUYER_NAME) is False
        assert names_match(BUYER_NAME, "") is False


# ── S1–S3 打分 + 排序 ──────────────────────────────────────


class TestScoreContractForInvoice:
    def test_s1_project_code_hit_scores_one(self) -> None:
        """真实样本：项目号命中 → kind=project_code，score=1.0。"""
        contract = _FakeContract(contract_id=101, name=REAL_CONTRACT_NAME, oa_number=PROJECT_CODE)

        candidate = score_contract_for_invoice(
            contract=contract,
            project_codes=extract_project_code_candidates(REMARK),
            case_text=REMARK,
            buyer_name=BUYER_NAME,
            today=INVOICE_DATE,
        )

        assert candidate is not None
        assert candidate.kind == KIND_PROJECT_CODE
        assert candidate.score == 1.0
        assert any(PROJECT_CODE in reason for reason in candidate.reasons)

    def test_s2_case_text_hit_without_project_code(self) -> None:
        """备注里没写项目号，但案由文字对得上合同名 → kind=case_text，score=0.7。"""
        contract = _FakeContract(contract_id=102, name=REAL_CONTRACT_NAME)

        candidate = score_contract_for_invoice(
            contract=contract,
            project_codes=[],
            case_text="张某与某公司合同纠纷",
            buyer_name="",
            today=INVOICE_DATE,
        )

        assert candidate is not None
        assert candidate.kind == KIND_CASE_TEXT
        assert candidate.score == pytest.approx(0.7)

    def test_s3_buyer_name_hit_scores_half(self) -> None:
        contract = _FakeContract(contract_id=103, name="无关项目名称", principals=[BUYER_NAME])

        candidate = score_contract_for_invoice(
            contract=contract, project_codes=[], case_text="", buyer_name=BUYER_NAME, today=INVOICE_DATE
        )

        assert candidate is not None
        assert candidate.kind == KIND_PARTY_NAME
        assert candidate.score == pytest.approx(0.5)

    def test_opposing_party_name_is_not_s3_evidence(self) -> None:
        """只认委托人：对方当事人出现在发票购买方一栏几乎不可能。"""
        contract = _FakeContract(contract_id=104, name="无关项目名称", opposing=[BUYER_NAME])

        assert (
            score_contract_for_invoice(
                contract=contract, project_codes=[], case_text="", buyer_name=BUYER_NAME, today=INVOICE_DATE
            )
            is None
        )

    def test_no_signal_returns_none(self) -> None:
        """S4（金额/日期）不参与打分：没有任何 S1–S3 信号就不进候选。"""
        contract = _FakeContract(contract_id=105, name="完全无关的项目", principals=["别人"])

        assert (
            score_contract_for_invoice(
                contract=contract, project_codes=[], case_text=REMARK, buyer_name=BUYER_NAME, today=INVOICE_DATE
            )
            is None
        )

    def test_expired_contract_gets_caveat_but_stays_candidate(self) -> None:
        contract = _FakeContract(
            contract_id=106, name=REAL_CONTRACT_NAME, oa_number=PROJECT_CODE, end_date=date(2026, 1, 1)
        )

        candidate = score_contract_for_invoice(
            contract=contract,
            project_codes=[PROJECT_CODE],
            case_text=REMARK,
            buyer_name=BUYER_NAME,
            today=INVOICE_DATE,
        )

        assert candidate is not None
        assert "到期" in candidate.caveat


class TestRankCandidates:
    def test_ordering_is_kind_first_then_score(self) -> None:
        """两个弱信号叠加（0.7+0.5=1.2）不得盖过一个确定信号（S1=1.0）。"""
        project = InvoiceCandidate(contract_id=1, contract_name="S1", kind=KIND_PROJECT_CODE, score=1.0)
        combined = InvoiceCandidate(contract_id=2, contract_name="S2+S3", kind=KIND_CASE_TEXT, score=1.2)
        party = InvoiceCandidate(contract_id=3, contract_name="S3", kind=KIND_PARTY_NAME, score=0.5)

        ranked = rank_candidates([party, combined, project])

        assert [c.contract_id for c in ranked] == [1, 2, 3]

    def test_limit_is_applied(self) -> None:
        candidates = [
            InvoiceCandidate(contract_id=i, contract_name=f"c{i}", kind=KIND_PARTY_NAME, score=0.5) for i in range(1, 8)
        ]

        assert len(rank_candidates(candidates, limit=3)) == 3


# ── S4：收款预选四级规则（用户已确认，不得改） ──────────────


class _RowsQuerySet:
    """``ContractPayment.objects.filter(...)`` 的替身：只实现被测代码用到的链式方法。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def order_by(self, *fields: str) -> _RowsQuerySet:
        return self

    def values(self, *fields: str) -> list[dict[str, Any]]:
        return list(self._rows)


class TestChoosePayment:
    """四个分支。收款查询用 mock 行集；分支判定与返回结构是真实代码。"""

    ROWS_ONE_MATCHING = [{"id": 12, "amount": Decimal("2400.00"), "received_at": INVOICE_DATE, "note": "尾款"}]
    ROWS_ONE_MISMATCH = [{"id": 13, "amount": Decimal("3000.00"), "received_at": INVOICE_DATE, "note": ""}]
    ROWS_MANY = [
        {"id": 21, "amount": Decimal("2400.00"), "received_at": date(2026, 10, 1), "note": "首款"},
        {"id": 22, "amount": Decimal("1000.00"), "received_at": date(2026, 11, 1), "note": "尾款"},
    ]

    @staticmethod
    def _run(rows: list[dict[str, Any]], amount: Decimal | None = TOTAL_AMOUNT) -> dict[str, Any]:
        from apps.contracts.models import ContractPayment

        with mock.patch.object(
            ContractPayment.objects,
            "filter",
            side_effect=lambda **kw: _RowsQuerySet(sorted(rows, key=lambda r: (r["received_at"], r["id"]))),
        ):
            return choose_payment(contract_id=999, total_amount=amount, invoice_date=INVOICE_DATE)

    def test_branch_one_single_payment_with_matching_amount(self) -> None:
        """① 恰好 1 笔且金额吻合 → 选它，confidence=exact。"""
        result = self._run(self.ROWS_ONE_MATCHING)

        assert result["suggested_payment_id"] == 12
        assert result["confidence"] == CONFIDENCE_EXACT
        assert result["note"] == ""
        assert [o["id"] for o in result["payment_options"]] == [12]
        assert result["payment_options"][0]["amount"] == "2400.00"
        assert result["payment_options"][0]["received_at"] == "2026-11-10"
        assert result["payment_options"][0]["note"] == "尾款"

    def test_branch_two_single_payment_amount_mismatch(self) -> None:
        """② 恰好 1 笔但金额不符 → 仍选它，confidence=amount_mismatch + 提示。"""
        result = self._run(self.ROWS_ONE_MISMATCH)

        assert result["suggested_payment_id"] == 13
        assert result["confidence"] == CONFIDENCE_AMOUNT_MISMATCH
        assert result["note"] == NOTE_AMOUNT_MISMATCH

    def test_branch_three_multiple_payments_is_ambiguous(self) -> None:
        """③ 多笔 → 不猜，suggested_payment_id=None。"""
        result = self._run(self.ROWS_MANY)

        assert result["suggested_payment_id"] is None
        assert result["confidence"] == CONFIDENCE_AMBIGUOUS
        assert result["note"] == NOTE_AMBIGUOUS
        assert [o["id"] for o in result["payment_options"]] == [21, 22]

    def test_branch_four_no_payment(self) -> None:
        """④ 无收款 → 先开票后付款。"""
        result = self._run([])

        assert result["suggested_payment_id"] is None
        assert result["confidence"] == CONFIDENCE_NO_PAYMENT
        assert result["note"] == NOTE_NO_PAYMENT
        assert result["payment_options"] == []

    def test_missing_invoice_amount_is_not_treated_as_match(self) -> None:
        """发票金额抽不到时不能算「金额吻合」——缺金额不是证据。"""
        result = self._run(self.ROWS_ONE_MATCHING, amount=None)

        assert result["confidence"] == CONFIDENCE_AMOUNT_MISMATCH
        assert result["suggested_payment_id"] == 12

    def test_amount_within_tolerance_counts_as_exact(self) -> None:
        """2400 与 2400.00 视为同一笔（绝对容差 0.005）。"""
        result = self._run(self.ROWS_ONE_MATCHING, amount=Decimal("2400"))

        assert result["confidence"] == CONFIDENCE_EXACT


# ── 对外入口：rank_invoice_candidates ──────────────────────


def _fake_eligible_qs(contracts: list[_FakeContract]):
    """替换 ``eligible_contract_qs``：返回可链式调用的假 QuerySet。"""

    class _FakeQS(list[_FakeContract]):
        def prefetch_related(self, *args: Any, **kwargs: Any) -> _FakeQS:
            return self

        def only(self, *fields: str) -> _FakeQS:
            return self

    return _FakeQS(contracts)


class TestRankInvoiceCandidates:
    def test_real_sample_hits_project_code_contract_as_top(self) -> None:
        """真实样本：备注里的项目号命中唯一合同 → 首选它，kind=project_code。

        合同/收款的**主键不硬编码**：id 只在本用例内临时编号，断言的是「同一份合同」
        而不是某个具体数字（换库/换环境不会假红）。
        """
        target = _FakeContract(contract_id=7, name=REAL_CONTRACT_NAME, oa_number=PROJECT_CODE, principals=[BUYER_NAME])
        noise = _FakeContract(contract_id=8, name="某供应链管理有限公司税务处理案", principals=["刘立德"])

        with (
            mock.patch(
                "apps.contracts.services.payment.invoice_match.eligible_contract_qs",
                return_value=_fake_eligible_qs([noise, target]),
            ),
            mock.patch(
                "apps.contracts.services.payment.invoice_match.collect_excluded_hints",
                return_value=[],
            ),
        ):
            result = rank_invoice_candidates(
                project_code=PROJECT_CODE, buyer_name=BUYER_NAME, remark=REMARK, original_filename=REAL_FILENAME
            )

        assert result["matcher_version"] == MATCHER_VERSION
        assert result["top_contract_id"] == target.id
        assert result["candidates"][0]["contract_id"] == target.id
        assert result["candidates"][0]["kind"] == KIND_PROJECT_CODE
        assert result["candidates"][0]["score"] == 1.0
        # 只有金额/日期、没有任何 S1–S3 证据的合同不进候选（S4 不单独拉候选）
        assert noise.id not in [c["contract_id"] for c in result["candidates"]]

    def test_project_code_found_in_filename_when_remark_is_bare(self) -> None:
        """备注没写项目号、项目号只印在附件名里时同样命中（税务平台自动命名）。"""
        target = _FakeContract(contract_id=9, name=REAL_CONTRACT_NAME, oa_number=PROJECT_CODE)

        with (
            mock.patch(
                "apps.contracts.services.payment.invoice_match.eligible_contract_qs",
                return_value=_fake_eligible_qs([target]),
            ),
            mock.patch("apps.contracts.services.payment.invoice_match.collect_excluded_hints", return_value=[]),
        ):
            result = rank_invoice_candidates(project_code="", buyer_name="", remark="", original_filename=REAL_FILENAME)

        assert result["top_contract_id"] == target.id
        assert result["project_codes"] == [PROJECT_CODE]

    def test_no_project_code_does_not_skip_other_signals(self) -> None:
        """`project_code` 为空时 S1 跳过，S2（案由文字）仍应命中。"""
        target = _FakeContract(contract_id=10, name=REAL_CONTRACT_NAME)

        with (
            mock.patch(
                "apps.contracts.services.payment.invoice_match.eligible_contract_qs",
                return_value=_fake_eligible_qs([target]),
            ),
            mock.patch("apps.contracts.services.payment.invoice_match.collect_excluded_hints", return_value=[]),
        ):
            result = rank_invoice_candidates(
                project_code="", buyer_name=BUYER_NAME, remark="张某与某公司合同纠纷", original_filename=""
            )

        assert result["top_contract_id"] == target.id
        assert result["candidates"][0]["kind"] in {KIND_CASE_TEXT, KIND_PARTY_NAME}

    def test_empty_snapshot_shape_when_nothing_matches(self) -> None:
        with (
            mock.patch(
                "apps.contracts.services.payment.invoice_match.eligible_contract_qs",
                return_value=_fake_eligible_qs([]),
            ),
            mock.patch("apps.contracts.services.payment.invoice_match.collect_excluded_hints", return_value=[]),
        ):
            result = rank_invoice_candidates(project_code="", buyer_name="", remark="", original_filename="")

        assert result["candidates"] == []
        assert result["top_contract_id"] is None
        assert set(result) == {
            "matcher_version",
            "computed_at",
            "candidates",
            "excluded_hints",
            "top_contract_id",
            "project_codes",
        }

    def test_candidate_dict_keys_are_snapshot_contract(self) -> None:
        target = _FakeContract(contract_id=11, name=REAL_CONTRACT_NAME, oa_number=PROJECT_CODE)

        with (
            mock.patch(
                "apps.contracts.services.payment.invoice_match.eligible_contract_qs",
                return_value=_fake_eligible_qs([target]),
            ),
            mock.patch("apps.contracts.services.payment.invoice_match.collect_excluded_hints", return_value=[]),
        ):
            result = rank_invoice_candidates(
                project_code=PROJECT_CODE, buyer_name=BUYER_NAME, remark=REMARK, original_filename=""
            )

        assert set(result["candidates"][0]) == {"contract_id", "contract_name", "kind", "score", "reasons", "caveat"}


# ── 真实 DB 路径 ──────────────────────────────────────────


#: 端到端用例依赖的表字段。缺任一列都会 ProgrammingError。
#:
#: 探测是为了让端到端用例在**陈旧 schema 的测试库**上跳过并说明原因，
#: 而不是假红（把 DB 环境问题当成代码 bug）或 xfail（静默通过）。
_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "contracts_contract": ("stages", "law_firm_oa_case_number", "fixed_amount", "fee_mode", "end_date"),
}


def _contract_table_schema_ready() -> tuple[bool, str]:
    """被测模型依赖的表结构是否已就绪。

    探测用 `information_schema` 而不是真实 SELECT：后者一旦失败会让连接进入
    aborted transaction 状态，把同一次会话里后续的 DB 用例一起拖红。
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            for table, required in _REQUIRED_COLUMNS.items():
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", [table])
                columns = {row[0] for row in cursor.fetchall()}
                missing = sorted(set(required) - columns)
                if missing:
                    return False, f"测试库 schema 陈旧（{table} 缺 {missing}），真实 ORM 落库路径未跑"
    except Exception as exc:
        return False, f"无法读取表结构：{exc.__class__.__name__}: {exc}"
    return True, ""


@pytest.fixture
def contract_table_schema_ready(db) -> tuple[bool, str]:
    """在 `db` 夹具允许访问数据库之后才探测表结构（探测本身要连接）。"""
    return _contract_table_schema_ready()


@pytest.mark.django_db
def test_rank_runs_against_real_database() -> None:
    """真实 DB 路径：无合格候选时也应返回合法快照结构，不抛异常。

    这里跑的是真实的 `eligible_contract_qs()`（含 paid_total 聚合、案件结案相关
    子查询）与真实的 `collect_excluded_hints()`，只读不写，陈旧 schema 也成立。
    """
    result = rank_invoice_candidates(project_code=PROJECT_CODE, buyer_name=BUYER_NAME, remark=REMARK)

    assert result["matcher_version"] == MATCHER_VERSION
    assert isinstance(result["candidates"], list)
    assert isinstance(result["excluded_hints"], list)
    assert result["project_codes"] == [PROJECT_CODE]
    for candidate in result["candidates"]:
        assert candidate["kind"] in {KIND_PROJECT_CODE, KIND_CASE_TEXT, KIND_PARTY_NAME}


@pytest.mark.django_db
def test_choose_payment_with_no_payment_in_real_table() -> None:
    """真实 DB 路径：不存在的合同没有收款 → 分支④ no_payment（查真实表，不走 mock）。"""
    result = choose_payment(contract_id=0, total_amount=TOTAL_AMOUNT, invoice_date=INVOICE_DATE)

    assert result["confidence"] == CONFIDENCE_NO_PAYMENT
    assert result["suggested_payment_id"] is None
    assert result["payment_options"] == []


@pytest.mark.django_db(transaction=True)
def test_s1_hits_real_contract_end_to_end(contract_table_schema_ready: tuple[bool, str]) -> None:
    """端到端（真实库）：项目号命中 → 唯一合同 → 唯一收款预选为 exact。

    合同与收款由本用例现建现取，**主键不硬编码**；所有写入都在用例事务内，
    退出即回滚（`transaction=True` 让被测代码里的 `eligible_contract_qs()` 看到本用例
    刚建的数据，同时不污染测试库）。
    """
    ready, reason = contract_table_schema_ready
    if not ready:
        pytest.skip(reason)

    from apps.client.models import Client
    from apps.contracts.models import Contract, ContractParty, ContractPayment

    suffix = uuid.uuid4().hex[:8].upper()
    oa_number = f"2099GZS{int(suffix[:4], 16) % 10000:04d}"
    contract = Contract.objects.create(
        name=f"测试委托人诉某公司合同纠纷案-{suffix}",
        status="active",
        fee_mode="FIXED",
        fixed_amount=Decimal("10000.00"),
        law_firm_oa_case_number=oa_number,
    )
    client = Client.objects.create(name=f"测试委托人{suffix}")
    ContractParty.objects.create(contract=contract, client=client, role="PRINCIPAL")
    payment = ContractPayment.objects.create(
        contract=contract, amount=TOTAL_AMOUNT, received_at=INVOICE_DATE, note="尾款"
    )

    snapshot = rank_invoice_candidates(
        project_code=oa_number,
        buyer_name=client.name,
        remark=f"{oa_number}-{client.name}与某公司合同纠纷;",
        original_filename="",
    )

    assert snapshot["top_contract_id"] == contract.id
    top = snapshot["candidates"][0]
    assert top["contract_id"] == contract.id
    assert top["kind"] == KIND_PROJECT_CODE
    assert top["score"] == 1.0

    chosen = choose_payment(contract.id, TOTAL_AMOUNT, INVOICE_DATE)
    assert chosen["suggested_payment_id"] == payment.id
    assert chosen["confidence"] == CONFIDENCE_EXACT
