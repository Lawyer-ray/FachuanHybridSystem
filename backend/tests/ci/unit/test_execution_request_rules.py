from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.cases.models import Case, CaseNumber
from apps.documents.services.placeholders.litigation.execution_request_service import ExecutionRequestService
from apps.finance.models.lpr_rate import LPRRate
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys


@pytest.fixture
def service() -> ExecutionRequestService:
    return ExecutionRequestService()


def _seed_lpr_rates() -> None:
    LPRRate.objects.create(
        effective_date=date(2023, 1, 1),
        rate_1y=Decimal("3.00"),
        rate_5y=Decimal("3.50"),
    )


@pytest.mark.django_db
def test_execution_request_rules_case_38361_deduction_order(service: ExecutionRequestService) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="38361测试", target_amount=Decimal("223841.55"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="(2025)粤0606民初38361号",
        document_name="民事调解书",
        document_content=(
            "一、原、被告协议一致确认，截止至2025年8月27日，被告张嘉良应向原告叶晓彤偿还借款190860元、利息36000元、律师代理费12000元、财产保全担保费800元，"
            "上述款项合计为239660元。"
            "二、本案受理费减半收取2456.93元，财产保全申请费1724.62元，合计4181.55元（原告叶晓彤已预交），由被告张嘉良负担并于2026年6月20日前直接支付给原告叶晓彤；"
            "三、若被告张嘉良有任何一期未按时足额支付上述款项的（协议签订后已支付的款项按顺序优先抵扣案件受理费、财产保全申请费、律师代理费、财产保全担保费、利息、借款），"
            "原告叶晓彤有权就被告张嘉良未支付的上述款项及利息（以未偿还的借款为基数，自2025年8月28日起按全国银行间同业拆借中心公布的一年期贷款市场报价利率的4倍计算至实际清偿之日止）"
            "一次性申请人民法院强制执行。"
        ),
        execution_paid_amount=Decimal("20000"),
        execution_use_deduction_order=True,
        execution_cutoff_date=date(2025, 10, 23),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["principal"] == "190860"
    assert params["confirmed_interest"] == "32981.55"
    assert params["attorney_fee"] == "0"
    assert params["guarantee_fee"] == "0"
    assert params["interest_base"] == "190860"
    assert "律师代理费" not in preview
    assert "担保费" not in preview


@pytest.mark.django_db
def test_execution_request_rules_case_254_fee_ownership_and_double_interest(service: ExecutionRequestService) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="254测试", target_amount=Decimal("212160.03"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2025）粤0608民初254号",
        document_name="民事判决书",
        document_content=(
            "一、被告江门市容普五金有限公司于本判决发生法律效力之日起十日内向原告佛山市高明合和盈新型材料有限公司支付货款 212160.03 元及逾期利息"
            "（以 212160.03 元为本金，按全国银行间同业拆借中心公布的一年期贷款市场报价利率的 1.3 倍从2023 年 10 月 1 日起计至实际清偿之日）；"
            "二、被告江门市容普五金有限公司于本判决发生法律效力之日起十日内向原告佛山市高明合和盈新型材料有限公司支付保全费 1639.94 元；"
            "本案受理费 4660 元（原告佛山市高明合和盈新型材料有限公司已交），由原告佛山市高明合和盈新型材料有限公司负担 36 元，被告江门市容普五金有限公司负担 4624 元。"
            "原告佛山市高明合和盈新型材料有限公司多预交的受理费 4624 元，由本院在本判决发生法律效力后予以退回。"
            "被告江门市容普五金有限公司负担的受理费 4624 元，由被告江门市容普五金有限公司在本判决发生法律效力之日起七日内向本院缴纳。"
            "公告费 200 元（原告佛山市高明合和盈新型材料有限公司已缴交），由被告江门市容普五金有限公司负担，并于支付判项确认的款项时迳付原告佛山市高明合和盈新型材料有限公司。"
            "如果未按本判决指定的期间履行给付金钱义务，应当依照《中华人民共和国民事诉讼法》第二百六十四条规定，加倍支付迟延履行期间的债务利息。"
        ),
        execution_cutoff_date=date(2025, 11, 25),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["litigation_fee"] == "0"
    assert params["preservation_fee"] == "1639.94"
    assert params["announcement_fee"] == "200"
    assert params["has_double_interest_clause"] is True
    assert "货款本金212160.03元" in preview
    assert "加倍支付迟延履行期间的债务利息" in preview
    assert "4624" not in preview
    assert any("受理费" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_rules_case_51548_fixed_rate_and_cap(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="51548测试", target_amount=Decimal("100592.83"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2025）粤1973民初51548号",
        document_name="民事调解书",
        document_content=(
            "一、原、被告一致确认，截至 2025 年 11 月 5 日两被告尚欠原告货款 100592.83 元；"
            "三、本案受理费 1467 元、（2025）粤 1973 财保 6689号财产保全费 1178 元，由原告预交，两被告负担并应于 2026年 3 月 30 日前一次性支付给原告；"
            "四、若两被告任何一期未能按时足额支付上述款项，原告有权要求两被告支付逾期付款利息（以 100592.83元的剩余未付款项为基数，"
            "自 2025 年 7 月 1 日起按年利率4.5%计算至实际清偿之日止，逾期付款利息总额以不超过100592.83 元为限），"
            "并有权要求就 100592.83 元的剩余未付款、受理费、财产保全费、逾期付款利息向法院申请一次性强制执行，"
            "已付款项按受理费、财产保全费、逾期付款利息、货款顺序进行抵扣。"
        ),
        execution_cutoff_date=date(2025, 12, 23),
        execution_use_deduction_order=True,
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["interest_cap"] == "100592.83"
    assert params["preservation_fee"] == "1178"
    assert params["litigation_fee"] == "1467"
    assert "受理费" in "".join(params["deduction_order"])
    assert "财产保全费" in preview
    assert "年利率4.5%" in preview


@pytest.mark.django_db
def test_execution_request_manual_text_has_priority(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="手工文本优先")
    CaseNumber.objects.create(
        case=case,
        number="(2026)测试1号",
        document_name="民事判决书",
        document_content="支付货款1000元。",
        execution_manual_text="这是手工填写的申请执行事项",
    )

    result = service.generate({"case_id": case.id})
    assert result[LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST] == "这是手工填写的申请执行事项"


@pytest.mark.django_db
def test_execution_request_cutoff_prefers_case_specified_date(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="指定日期优先", target_amount=Decimal("1000"), specified_date=date(2025, 12, 31))
    case_number = CaseNumber.objects.create(
        case=case,
        number="(2026)测试2号",
        document_name="民事判决书",
        document_content=(
            "被告应向原告偿还借款1000元。"
            "逾期利息以1000元为本金，自2025年1月1日起按年利率4.5%计算至实际清偿之日。"
        ),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    assert result["structured_params"]["cutoff_date"] == "2025-12-31"


@pytest.mark.django_db
def test_execution_request_cutoff_falls_back_to_today_when_no_specified_date(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="默认今天", target_amount=Decimal("1000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="(2026)测试3号",
        document_name="民事判决书",
        document_content=(
            "被告应向原告偿还借款1000元。"
            "逾期利息以1000元为本金，自2025年1月1日起按年利率4.5%计算至实际清偿之日。"
        ),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    assert result["structured_params"]["cutoff_date"] == date.today().isoformat()


@pytest.mark.django_db
def test_execution_request_parses_lpr_markup_percent_as_multiplier(service: ExecutionRequestService) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="上浮百分比解析", target_amount=Decimal("93633"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="(2025)测试4号",
        document_name="民事判决书",
        document_content=(
            "一、被告在本判决发生法律效力之日起十日内向原告支付货款93633元；"
            "二、被告在本判决发生法律效力之日起十日内向原告支付利息"
            "（利息以93633元为基数，从2025年4月8日起按全国银行间同业拆借中心公布的一年期贷款市场报价利率上浮50%计算至实际清偿之日止）；"
        ),
        execution_cutoff_date=date(2025, 10, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]

    assert params["interest_rate_description"].endswith("1.5倍")
    assert params["overdue_interest"] == "2329.12"


@pytest.mark.django_db
def test_execution_request_rules_case_34475_chinese_multiplier_and_fee_variants(
    service: ExecutionRequestService,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="34475测试", target_amount=Decimal("2500000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2024）粤0606民初34475号",
        document_name="民事调解书",
        document_content=(
            "一、原、被告一致确认：截止至 2024 年 12 月 11 日，被告邱豪尚欠原告曾昭志借款本金 2500000 元，该款由被告邱豪在2025 年 6 月 30 日前一次性偿还给原告曾昭志；"
            "二、被告邱豪同意承担原告曾昭志因本案诉讼支出的律师费72000 元，该款由被告邱豪在 2025 年 6 月 30 日前一并返还给原告曾昭志；"
            "三、本案受理费减半收取为 14028.67 元（原告已预交），由被告邱豪承担，定于 2025 年 6 月 30 日前一并返还给原告曾昭志。"
            "四、如被告邱豪未按上述第一、二、三项约定按期足额还款的，则原告曾昭志有权就被告邱豪未还的剩余借款本金、律师费、受理费一次性向法院申请强制执行，"
            "并有权以剩余未还借款本金为基数按全国银行间同业拆借中心公布的同期一年期贷款市场报价利率四倍自2024年6 月1 日起计收逾期还款利息至被告邱豪还清该笔借款本金之日止。"
        ),
        execution_paid_amount=Decimal("800000"),
        execution_cutoff_date=date(2025, 7, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["principal"] == "1700000"
    assert params["attorney_fee"] == "72000"
    assert params["litigation_fee"] == "14028.67"
    assert params["interest_base"] == "1700000"
    assert params["interest_rate_description"].endswith("4倍")
    assert params["interest_start_date"] == "2024-06-01"
    assert params["cutoff_date"] == "2025-07-23"
    assert params["overdue_interest"] == "236866.67"
    assert "律师代理费72000元" in preview
    assert "受理费14028.67元" in preview


@pytest.mark.django_db
def test_execution_request_fee_marker_yifu_and_interest_base_reduces_after_paid(
    service: ExecutionRequestService,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="迳付予原告与本金扣减", target_amount=Decimal("732000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2024）测试5号",
        document_name="民事判决书",
        document_content=(
            "佛山市南海区祥财云海装饰五金厂应向佛山市宝皆铝业有限公司支付货款732000元及利息"
            "（以732000元为基数，自2024年5月1日起至实际清偿之日止，按全国银行间同业拆借中心公布的一年期贷款市场报价利率的1.3倍计算）。"
            "财产保全费4422.61元（原告已缴纳），由被告共同负担并应于本判决发生法律效力之日起十日内迳付予原告。"
            "如果未按本判决指定的期间履行给付金钱义务，应当加倍支付迟延履行期间的债务利息。"
        ),
        execution_paid_amount=Decimal("362780"),
        execution_cutoff_date=date(2025, 5, 8),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["principal"] == "369220"
    assert params["interest_base"] == "369220"
    assert params["overdue_interest"] == "14919.56"
    assert params["preservation_fee"] == "4422.61"
    assert "财产保全费4422.61元" in preview


@pytest.mark.django_db
def test_execution_request_rules_case_520000_wan_unit_and_fee_burden_and_double_interest(
    service: ExecutionRequestService,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="52万元解析测试", target_amount=Decimal("520000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2024）测试6号",
        document_name="民事判决书",
        document_content=(
            "一、被告谭英兰应自本判决发生法律效力之日起十五日内向原告何凤鸣归还借款本金 52 万元及支付逾期利息"
            "（逾期利息计算方式：以 52 万元为基数，从 2024 年 6 月 8 日起按一年期 LPR 四倍计算至清偿之日止）；"
            "二、被告谭英兰应自本判决发生法律效力之日起十五日内向原告何凤鸣支付律师费 21000元、财产保全担保费1110.77 元。"
            "如果未按本判决指定的期间履行给付金钱义务，应当依《中华人民共和国民事诉讼法》第二百六十四条之规定，"
            "加倍支付迟 延履行期间的债务利息。"
            "本案受理费减半收取计 4682.47 元，诉前财产保全费3296.92元，合计共 7979.39元（原告已预交），由被告谭英兰负担。"
        ),
        execution_cutoff_date=date(2025, 1, 21),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["principal"] == "520000"
    assert params["interest_base"] == "520000"
    assert params["overdue_interest"] == "39520"
    assert params["litigation_fee"] == "4682.47"
    assert params["preservation_fee"] == "3296.92"
    assert params["has_double_interest_clause"] is True
    assert "加倍支付迟延履行期间的债务利息" in preview
    assert not any("未从文书解析到本金" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_ollama_fallback_merges_when_rules_low_confidence(
    service: ExecutionRequestService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="LLM兜底测试", target_amount=Decimal("1000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2024）测试7号",
        document_name="民事判决书",
        document_content=(
            "被告应向原告归还借款本金伍拾贰万元。"
            "逾期利息以伍拾贰万元为基数，自2024年6月8日起按一年期LPR四倍计算至清偿之日止。"
            "若未按期履行，应加倍支付迟延履行期间的债务利息。"
        ),
        execution_cutoff_date=date(2025, 1, 21),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    monkeypatch.setattr(
        service,
        "_extract_with_ollama_fallback",
        lambda _text: {
            "principal_amount": Decimal("520000"),
            "principal_label": "借款本金",
            "interest_start_date": date(2024, 6, 8),
            "interest_base_amount": Decimal("520000"),
            "lpr_multiplier": Decimal("4"),
            "fixed_rate_percent": Decimal("0"),
            "litigation_fee": Decimal("0"),
            "preservation_fee": Decimal("0"),
            "announcement_fee": Decimal("0"),
            "attorney_fee": Decimal("0"),
            "guarantee_fee": Decimal("0"),
            "has_double_interest_clause": True,
        },
    )

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["principal"] == "520000"
    assert params["interest_base"] == "520000"
    assert params["overdue_interest"] == "39520"
    assert params["has_double_interest_clause"] is True
    assert params["llm_fallback_used"] is True
    assert "加倍支付迟延履行期间的债务利息" in preview


@pytest.mark.django_db
def test_execution_request_ollama_fallback_can_be_disabled(
    service: ExecutionRequestService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="LLM兜底开关关闭", target_amount=Decimal("1000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2024）测试8号",
        document_name="民事判决书",
        document_content=(
            "被告应向原告归还借款本金伍拾贰万元。"
            "逾期利息以伍拾贰万元为基数，自2024年6月8日起按一年期LPR四倍计算至清偿之日止。"
        ),
        execution_cutoff_date=date(2025, 1, 21),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    def _should_not_call(_text: str) -> dict[str, object]:
        raise AssertionError("llm fallback should not be called")

    monkeypatch.setattr(service, "_extract_with_ollama_fallback", _should_not_call)

    result = service.preview_for_case_number(
        case=case,
        case_number=case_number,
        enable_llm_fallback=False,
    )
    params = result["structured_params"]

    assert params["llm_fallback_enabled"] is False
    assert params["llm_fallback_used"] is False
