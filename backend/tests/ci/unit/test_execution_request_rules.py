from __future__ import annotations

import re
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
    assert "货款212160.03元" in preview
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
def test_execution_request_generate_converts_manual_newlines_to_docx_hard_breaks(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="手工文本换行转换")
    CaseNumber.objects.create(
        case=case,
        number="(2026)测试1-1号",
        document_name="民事判决书",
        document_content="支付货款1000元。",
        execution_manual_text="第一行\n第二行",
    )

    result = service.generate({"case_id": case.id})
    output = result[LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST]

    assert output == "第一行\a第二行"
    assert "\n" not in output


@pytest.mark.django_db
def test_execution_request_generate_output_uses_docx_hard_breaks(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="规则输出换行转换", target_amount=Decimal("1000"))
    CaseNumber.objects.create(
        case=case,
        number="(2026)测试1-2号",
        document_name="民事判决书",
        document_content="被告应向原告偿还借款1000元。",
    )

    result = service.generate({"case_id": case.id})
    output = result[LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST]

    assert "\a" in output
    assert "\n" not in output


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
def test_execution_request_infers_principal_from_interest_base_and_lpr_standard(service: ExecutionRequestService) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="租赁费用按LPR标准", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2025）测试4-1号",
        document_name="民事判决书",
        document_content=(
            "一、被告应于本判决发生法律效力之日起五日内向原告支付吊车租赁费用27334元及利息"
            "（利息以27334元为基数，自2024年8月11日起按同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的标准，"
            "计算至实际清偿完毕之日止）；"
        ),
        execution_cutoff_date=date(2024, 9, 10),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(
        case=case,
        case_number=case_number,
        enable_llm_fallback=False,
    )
    params = result["structured_params"]
    warnings = result["warnings"]

    assert params["principal"] == "27334"
    assert params["interest_base"] == "27334"
    assert params["interest_rate_description"] == "全国银行间同业拆借中心公布的一年期贷款市场报价利率"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert not any("回退使用案件“涉案金额”" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_lpr_standard_clause_does_not_trigger_llm_fallback_when_rules_sufficient(
    service: ExecutionRequestService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="LPR标准不触发兜底", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2025）测试4-2号",
        document_name="民事判决书",
        document_content=(
            "一、被告应于本判决发生法律效力之日起五日内向原告支付吊车租赁费用27334元及利息"
            "（利息以27334元为基数，自2024年8月11日起按同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的标准，"
            "计算至实际清偿完毕之日止）；"
            "本案受理费504元、保全费302元，由被告负担。"
        ),
        execution_cutoff_date=date(2024, 9, 10),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    def _should_not_call(_text: str) -> dict[str, object]:
        raise AssertionError("llm fallback should not be called")

    monkeypatch.setattr(service, "_extract_with_ollama_fallback", _should_not_call)

    result = service.preview_for_case_number(case=case, case_number=case_number)
    params = result["structured_params"]

    assert params["principal"] == "27334"
    assert params["interest_rate_description"] == "全国银行间同业拆借中心公布的一年期贷款市场报价利率"
    assert params["llm_fallback_used"] is False


@pytest.mark.django_db
def test_execution_request_preview_text_has_no_numeric_prefix(service: ExecutionRequestService) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="执行事项去序号", target_amount=Decimal("1000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）测试9号",
        document_name="民事判决书",
        document_content=(
            "被告应向原告归还借款本金1000元。"
            "逾期利息以1000元为基数，自2025年1月1日起按一年期LPR计算至清偿之日止。"
            "如果未按期履行，应加倍支付迟延履行期间的债务利息。"
        ),
        execution_cutoff_date=date(2025, 1, 21),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    preview = result["preview_text"]

    for line in preview.splitlines():
        assert not re.match(r"^\d+\.", line)


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


@pytest.mark.django_db
def test_execution_request_fee_split_uses_defendant_burden_amount(service: ExecutionRequestService) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="费用分摊取被告负担", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）测试分摊号",
        document_name="民事判决书",
        document_content=(
            "被告吴某甲于本判决发生法律效力之日起十五日内向原告广州市某有限公司支付货款255552元及逾期付款损失"
            "（以255552元为基数，自2025年11月13日起按同期全国银行间同业拆借中心公布的一年期贷款市场报价利率上浮50%的标准计算至实际付清之日止）；"
            "如未按本判决指定的期间履行给付金钱义务，应当依照《中华人民共和国民事诉讼法》第二百六十四条的规定，加倍支付迟延履行期间的债务利息。"
            "案件受理费5464元，财产保全费1907.97元，合计为7371.97元，由原告广州市某有限公司负担614.97元，"
            "被告吴某甲负担6757元（于本判决发生法律效力之日起十五日内迳付原告广州市某有限公司）。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]

    assert params["litigation_fee"] == "4849.03"
    assert params["preservation_fee"] == "1907.97"
    assert Decimal(params["litigation_fee"]) + Decimal(params["preservation_fee"]) == Decimal("6757")


@pytest.mark.django_db
def test_execution_request_includes_supplementary_liability_clause(service: ExecutionRequestService) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="补充赔偿责任条款", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）补充责任测试号",
        document_name="民事判决书",
        document_content=(
            "被告广东某有限公司于本判决发生法律效力之日起十日内向原告广州市某有限公司支付货款692950元及利息"
            "（以692950元为基数，自2024年6月1日按全国银行间同业拆借中心公布的一年期贷款市场报价利率上浮50%计算至付清款日止）；"
            "被告梁某在未出资本息范围内对被告广东某有限公司上述债务不能清偿部分承担补充赔偿责任；"
            "如果未按本判决指定的期间履行给付金钱义务，应当加倍支付迟延履行期间的债务利息。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    preview = result["preview_text"]
    params = result["structured_params"]

    expected_clause = "被告梁某在未出资本息范围内对被告广东某有限公司上述债务不能清偿部分承担补充赔偿责任。"
    assert expected_clause in preview
    assert params["has_supplementary_liability_clause"] is True
    assert params["supplementary_liability_text"] == expected_clause.rstrip("。")


@pytest.mark.django_db
def test_execution_request_supports_segmented_interest_with_custom_rate(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="分段计息-自定义年利率", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）分段计息测试号",
        document_name="民事判决书",
        document_content=(
            "被告林某于本判决发生法律效力之日起十日内向原告阮某支付尚欠货款10766元；"
            "被告林某于本判决发生法律效力之日起十日内向原告阮某支付逾期付款损失"
            "（以11766元为基数，自2024年3月9日起按照年利率5.175%计算至2024年6月19日止；"
            "以10766元为基数，自2024年6月20日起按照年利率5.175%计算至实际清偿之日止）。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    preview = result["preview_text"]
    params = result["structured_params"]

    assert params["interest_segmented"] is True
    assert len(params["interest_segments"]) == 2
    assert params["interest_segments"][0] == {
        "base_amount": "11766",
        "start_date": "2024-03-09",
        "end_date": "2024-06-19",
    }
    assert params["interest_segments"][1] == {
        "base_amount": "10766",
        "start_date": "2024-06-20",
        "end_date": "",
    }
    assert params["interest_rate_description"] == "年利率5.18%"
    assert params["interest_base"] == "11766"
    assert "逾期付款损失" in preview
    assert "暂计至2026年3月23日逾期付款损失为" in preview
    assert "以11766元为基数" in preview
    assert "以10766元为基数" in preview


@pytest.mark.django_db
def test_execution_request_fee_split_single_item_uses_defendant_burden_amount(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="单项费用分摊扣减", target_amount=Decimal("1000"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）单项费用分摊号",
        document_name="民事判决书",
        document_content=(
            "被告应向原告支付借款1000元。"
            "案件受理费12401.27元，由原告承担1599元，被告承担10802.27元（向原告迳付）。"
        ),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["litigation_fee"] == "10802.27"
    assert "受理费10802.27元" in preview


@pytest.mark.django_db
def test_execution_request_complex_segmented_lpr_with_joint_liability_and_guarantee_fee(
    service: ExecutionRequestService,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="复杂分段计息样本", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）复杂样本号",
        document_name="民事判决书",
        document_content=(
            "被告广州市某有限公司于本判决生效之日起十日内向原告佛山市南海某有限公司支付货款604508.56元及违约金"
            "（违约金计算方法：以2022年12月欠付的货款254098.4元为基数自2023年2月5日起计算至2024年4月29日，"
            "以204098.4元为基数自2024年4月30日起计算至2024年5月6日，"
            "以194098.4元为基数自2024年5月7日起计算至2024年9月13日，"
            "以144098.4元为基数自2024年9月14日计算至实际清偿之日；"
            "以2023年1月、2月欠付货款252892.26元为基数自2023年4月17日起计算至实际清偿之日；"
            "以2023年3月欠付货款258628.3元为基数自2023年6月15日起计算至2023年7月14日；"
            "以2023年3月、4月、5月欠付货款207517.9元为基数自2023年7月15日起计算至实际清偿之日；"
            "以上均按照全国银行间同业拆借中心公布的一年期贷款市场报价利率1.5倍标准计算）；"
            "被告广州市某有限公司于本判决生效之日起十日内向原告佛山市南海某有限公司支付担保费1386元；"
            "被告冯某甲对本判决第一项确定的被告广州市某有限公司的债务承担连带责任；"
            "案件受理费12401.27元，由原告佛山市南海某有限公司承担1599元，被告广州市某有限公司、冯某甲承担10802.27元（向原告佛山市南海某有限公司迳付）；"
            "财产保全费4843元，由原告佛山市南海某有限公司承担624.45元，被告广州市某有限公司、冯某甲承担4218.55元（向原告佛山市南海某有限公司迳付）。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    preview = result["preview_text"]
    params = result["structured_params"]

    assert params["interest_segmented"] is True
    assert len(params["interest_segments"]) == 7
    assert params["interest_segments"][0] == {
        "base_amount": "254098.4",
        "start_date": "2023-02-05",
        "end_date": "2024-04-29",
    }
    assert params["interest_segments"][-1] == {
        "base_amount": "144098.4",
        "start_date": "2024-09-14",
        "end_date": "",
    }
    assert params["interest_rate_description"] == "全国银行间同业拆借中心公布的一年期贷款市场报价利率的1.5倍"
    assert params["guarantee_fee"] == "1386"
    assert params["litigation_fee"] == "10802.27"
    assert params["preservation_fee"] == "4218.55"
    assert params["has_joint_liability_clause"] is True
    assert "承担连带责任" in params["joint_liability_text"]
    assert "违约金" in preview
    assert "暂计至2026年3月23日违约金为" in preview
    assert "承担连带责任" in preview


@pytest.mark.django_db
def test_execution_request_parses_qingchang_principal_and_daily_percent_rate(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="清偿+每日百分比利率", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）每日利率测试号",
        document_name="民事判决书",
        document_content=(
            "在本判决发生法律效力之日起十日内，被告袁某向原告广州某有限公司第一分公司清偿货款12831.39元及该款违约金"
            "（从2025年3月3日起按照每日0.015%标准计至款项付清之日止）。"
            "如未按本判决指定的期间履行给付金钱义务，应当加倍支付迟延履行期间的债务利息。"
            "案件受理费10元，由被告袁某迳付给原告广州某有限公司第一分公司。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["principal"] == "12831.39"
    assert params["interest_start_date"] == "2025-03-03"
    assert params["interest_rate_description"] == "日利率0.015%"
    assert params["litigation_fee"] == "10"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert "受理费10元" in preview
    assert not warnings


@pytest.mark.django_db
def test_execution_request_parses_daily_permyriad_with_chinese_numeral(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="每日万分之中文数字", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）每日万分测试号",
        document_name="民事判决书",
        document_content=(
            "被告佛山某有限公司应于本判决发生法律效力之日起十日内向原告广州市某有限公司支付佣金39117621.61元及相应的利息"
            "（以39117621.61元为基数，自2025年1月4日起按照每日万分之三的标准计算至实际清偿之日止）。"
            "如果未按本判决指定的期间履行给付金钱义务的，应当依照《中华人民共和国民事诉讼法》第二百六十四条之规定，加倍支付迟延履行期间的债务利息。"
            "本案受理费244957.37元、保全费5000元，由被告佛山某有限公司负担。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    warnings = result["warnings"]

    assert params["principal"] == "39117621.61"
    assert params["interest_start_date"] == "2025-01-04"
    assert params["interest_rate_description"] == "日利率万分之3"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert params["litigation_fee"] == "0"
    assert params["preservation_fee"] == "0"
    assert any("受理费244957.37元已排除" in w for w in warnings)
    assert any("财产保全费5000元已排除" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_parses_segmented_lpr_start_only_and_insufficient_property_liability(
    service: ExecutionRequestService,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="分段起算+不足清偿责任", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）分段起算测试号",
        document_name="民事判决书",
        document_content=(
            "一、被告某有限公司广州分公司应在本判决发生法律效力之日起五日内向原告广东某有限公司支付货款23512912.89元；"
            "二、被告某有限公司广州分公司应在本判决发生法律效力之日起五日内向原告广东某有限公司支付利息"
            "（利息以分段计算以16459039元为基数，自2024年5月10日起算；"
            "以23512912.89元为基数，自2025年1月2日起算，"
            "均按同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的标准计算至实际清偿之日止）；"
            "三、被告某有限公司广州分公司财产不足清偿部分，由被告某有限公司承担清偿责任；"
            "四、驳回原告广东某有限公司的其余诉讼请求。"
            "如果未按本判决确定的期间履行给付金钱义务，应当依照《中华人民共和国民事诉讼法》第二百六十四条之规定，"
            "加倍支付迟延履行期间的债务利息。"
            "案件受理费164174.3元，由原告广东某有限公司负担3100.36元，由被告某有限公司广州分公司、某有限公司负担161073.94元；"
            "保全费5000元，由被告某有限公司广州分公司、某有限公司负担。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["principal"] == "23512912.89"
    assert params["interest_segmented"] is True
    assert len(params["interest_segments"]) == 2
    assert params["interest_segments"][0] == {
        "base_amount": "16459039",
        "start_date": "2024-05-10",
        "end_date": "",
    }
    assert params["interest_segments"][1] == {
        "base_amount": "23512912.89",
        "start_date": "2025-01-02",
        "end_date": "",
    }
    assert params["interest_rate_description"] == "全国银行间同业拆借中心公布的一年期贷款市场报价利率"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert params["has_supplementary_liability_clause"] is True
    assert "财产不足清偿部分" in params["supplementary_liability_text"]
    assert "承担清偿责任" in preview
    assert any("受理费164174.3元已排除" in w for w in warnings)
    assert any("财产保全费5000元已排除" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_supports_fee_only_items_without_principal(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="仅费用项生成", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）费用项测试号",
        document_name="民事判决书",
        document_content=(
            "在本判决发生法律效力之日起十日内，被告广州某公司一次性向原告某（广东）有限公司支付保全申请费5000元；"
            "如果未按本判决指定的期间履行给付金钱义务的，应当加倍支付迟延履行期间的债务利息。"
            "本案受理费216700元，由被告广州某公司负担。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    preview = result["preview_text"]
    params = result["structured_params"]
    warnings = result["warnings"]

    assert params["principal"] == "0"
    assert params["preservation_fee"] == "5000"
    assert params["litigation_fee"] == "0"
    assert params["total"] == "5000"
    assert "支付财产保全费5000元" in preview
    assert not any("未能确定本金" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_supports_multiple_overdue_interest_rules_with_mixed_rates(
    service: ExecutionRequestService,
) -> None:
    _seed_lpr_rates()
    case = Case.objects.create(name="多判项多利率逾期利息", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）多利率测试号",
        document_name="民事判决书",
        document_content=(
            "一、被告苏州某有限公司于本判决发生法律效力之日起十五日内向原告大得数智科技(广州)有限公司支付借款12000000元、借期内利息320000元及逾期利息"
            "（逾期利息分别以8000000元为本金自2021年12月22日起，以4000000元为本金自2022年2月10日起，均按年利率8%计算至实际清偿之日止）；"
            "二、被告苏州某有限公司于本判决发生法律效力之日起十五日内向原告大得数智科技(广州)有限公司支付借款14000000元、借期内利息1400000元及逾期利息"
            "（逾期利息以14000000元为本金自2023年1月27日起按同期中国人民银行授权全国银行间同业拆借中心公布的一年期贷款市场报价利率的四倍标准计算至实际清偿之日止）；"
            "三、被告苏州某有限公司于本判决发生法律效力之日起十五日内向原告大得数智科技(广州)有限公司支付律师费300000元。"
            "如果被告未按本判决指定的期间履行给付金钱义务，应当依照《中华人民共和国民事诉讼法》第二百六十四条之规定，加倍支付迟延履行期间的债务利息。"
            "案件受理费227128.23元，由原告大得数智科技(广州)有限公司负担40883元，由被告苏州某有限公司负担186245.23元。"
            "诉讼保全费5000元，由被告苏州某有限公司负担。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["principal"] == "26000000"
    assert params["confirmed_interest"] == "1720000"
    assert params["attorney_fee"] == "300000"
    assert params["has_multiple_overdue_interest_rules"] is True
    assert len(params["overdue_interest_rules"]) == 2
    assert params["overdue_interest_rules"][0]["interest_rate_description"] == "年利率8%"
    assert params["overdue_interest_rules"][0]["interest_segmented"] is True
    assert len(params["overdue_interest_rules"][0]["interest_segments"]) == 2
    assert params["overdue_interest_rules"][1]["interest_rate_description"] == "全国银行间同业拆借中心公布的一年期贷款市场报价利率的4倍"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert "逾期利息按判决确定的分项规则计算" in preview
    assert any("受理费227128.23元已排除" in w for w in warnings)
    assert any("财产保全费5000元已排除" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_handles_penalty_and_compound_interest_clause(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="罚息复利复杂条款", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）罚息复利测试号",
        document_name="民事判决书",
        document_content=(
            "一、被告广州市某丙有限公司于本判决发生法律效力之日起十日内向原告广州某有限公司增城支行偿还借款本金25924250.16元，并支付利息、罚息、复利"
            "（截至2025年6月12日的利息293854.17元、罚息748622.17元、复利15339.43元，自2025年6月13日起的罚息以尚欠借款本金25924250.16元为基数、"
            "复利以欠付利息293854.17元为基数，均按约定利率加收50%的标准计算至债务清偿之日止。上述利息、罚息和复利的利率合计不得超过年利率24%，罚息不计收复利）。"
            "二、被告广州市某己有限公司、广州市某甲有限公司、广州市某庚有限公司、广州市某乙有限公司、广东增城某有限公司、苗某、刘某对被告广州市某丙有限公司上述第一项债务承担连带清偿责任。"
            "案件受理费172411.45元，由被告广州市某庚有限公司、广州市某己有限公司、广州市某甲有限公司、广州市某丙有限公司、广州市某乙有限公司、广东增城某有限公司、广州市某戊有限公司、广东某有限公司、苗某、刘某共同负担。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["principal"] == "25924250.16"
    assert params["confirmed_interest"] == "1057815.77"
    assert params["has_joint_liability_clause"] is True
    assert "承担连带清偿责任" in params["joint_liability_text"]
    assert params["interest_segmented"] is True
    assert len(params["interest_segments"]) == 2
    assert params["interest_start_date"] == "2025-06-13"
    assert params["interest_rate_description"] == "年利率24%"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert "利息按分段基数计算" in preview
    assert any("受理费172411.45元已排除" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_includes_priority_execution_clauses(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="优先受偿权条款提取", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）优先受偿测试号",
        document_name="民事判决书",
        document_content=(
            "一、被告甲公司于本判决生效之日起十日内向原告乙银行偿还借款本金1000000元。"
            "二、原告乙银行对被告甲公司名下某地块的土地折价、拍卖或变卖所得价款在上述第一项确定的债权范围内按抵押顺位享有优先受偿权。"
            "三、原告乙银行对被告丙公司持有的甲公司股权折价或拍卖、变卖所得价款在上述第一项确定的债权范围内享有优先受偿权。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["has_priority_execution_clauses"] is True
    assert len(params["priority_execution_clauses"]) == 2
    assert "土地折价、拍卖或变卖所得价款" in params["priority_execution_clauses"][0]
    assert "股权折价或拍卖、变卖所得价款" in params["priority_execution_clauses"][1]
    assert "土地折价、拍卖或变卖所得价款" in preview
    assert "股权折价或拍卖、变卖所得价款" in preview


@pytest.mark.django_db
def test_execution_request_fallbacks_unrecognized_property_clause_for_manual_review(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="人工兜底条款", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）人工兜底测试号",
        document_name="民事判决书",
        document_content=(
            "一、被告甲公司于本判决生效之日起十日内向原告乙银行偿还借款本金2000000元。"
            "二、原告乙银行对被告甲公司名下应收账款在上述第一项确定的债权范围内享有优先受偿权。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["has_priority_execution_clauses"] is False
    assert params["has_manual_review_clauses"] is True
    assert len(params["manual_review_clauses"]) == 1
    assert "应收账款在上述第一项确定的债权范围内享有优先受偿权" in params["manual_review_clauses"][0]
    assert "【人工核对】" in preview
    assert "应收账款在上述第一项确定的债权范围内享有优先受偿权" in preview


@pytest.mark.django_db
def test_execution_request_supports_same_base_two_phase_rates_fixed_then_lpr(
    service: ExecutionRequestService,
) -> None:
    _seed_lpr_rates()
    LPRRate.objects.create(
        effective_date=date(2020, 1, 1),
        rate_1y=Decimal("3.85"),
        rate_5y=Decimal("4.65"),
    )
    case = Case.objects.create(name="同一基数双阶段利率", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）双阶段利率测试号",
        document_name="民事判决书",
        document_content=(
            "一、被告广州某创某港城投房地产开发有限公司于本判决发生法律效力之日起十日内向原告广州某港建设运营集团有限公司偿还借款30000000元；"
            "二、被告广州某创某港城投房地产开发有限公司在本判决发生法律效力之日起十日内向原告广州某港建设运营集团有限公司支付利息"
            "（以9000000元为基数，从2021年3月22日起按照年利率6%计算至2022年3月21日，从2022年3月22日起按照同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的四倍计算至偿还之日止；"
            "以4477500元为基数，从2021年4月27日至2022年4月26日按照年利率6%计算，从2022年4月27日起按照同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的四倍计算至偿还之日止；"
            "以5000000元为基数，从2021年7月9日起至2022年7月8日按照年利率6%计算，从2022年7月9日起按照同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的四倍计算至偿还之日止；"
            "以10450000元为基数，从2022年9月20日起至2023年9月19日按照年利率6%计算，从2023年9月20日按照同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的四倍计算至到偿还之日止；"
            "以1072500元为基数，从2022年9月23日起至2023年9月22日按照年利率6%计算，从2023年9月23日起按照同期全国银行间同业拆借中心公布的一年期贷款市场报价利率的四倍到计算至偿还之日止）；"
            "三、被告广州某创某港城投房地产开发有限公司于本判决发生法律效力之日起十日内向原告广州某港建设运营集团有限公司偿还借款808650元。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["principal"] == "30808650"
    assert params["has_multiple_overdue_interest_rules"] is True
    assert len(params["overdue_interest_rules"]) == 2
    fixed_rule = next(rule for rule in params["overdue_interest_rules"] if rule["interest_rate_description"] == "年利率6%")
    lpr_rule = next(rule for rule in params["overdue_interest_rules"] if "4倍" in rule["interest_rate_description"])
    assert fixed_rule["interest_segmented"] is True
    assert len(fixed_rule["interest_segments"]) == 5
    assert fixed_rule["interest_segments"][0]["start_date"] == "2021-03-22"
    assert fixed_rule["interest_segments"][0]["end_date"] == "2022-03-21"
    assert lpr_rule["interest_segmented"] is True
    assert len(lpr_rule["interest_segments"]) == 5
    assert lpr_rule["interest_segments"][0]["start_date"] == "2022-03-22"
    assert lpr_rule["interest_segments"][1]["start_date"] == "2022-04-27"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert "逾期利息按判决确定的分项规则计算" in preview


@pytest.mark.django_db
def test_execution_request_parses_advertising_fee_as_primary_principal(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="广告费主项本金识别", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）广告费主项号",
        document_name="民事判决书",
        document_content=(
            "被告广州某有限公司于本判决生效之日起十日内向原告海南某有限公司支付广告费17859734元；"
            "被告广州某有限公司于本判决生效之日起十日内向原告海南某有限公司支付逾期付款违约金"
            "（以1797120元为基数自2024年1月17日起；以1198080元为基数自2024年4月17日起，"
            "均按照每日万分之一的标准计算至实际清偿之日止）。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]

    assert params["principal"] == "17859734"
    assert params["principal_label"] == "广告费"
    assert params["overdue_interest_label"] == "逾期付款违约金"
    assert params["interest_segmented"] is True
    assert len(params["interest_segments"]) == 2
    assert params["interest_rate_description"] == "日利率万分之1"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert "广告费17859734元" in preview
    assert "逾期付款违约金" in preview
    assert "暂计至2026年3月23日逾期付款违约金为" in preview


@pytest.mark.django_db
def test_execution_request_parses_repurchase_price_with_annualized_rate_segments(
    service: ExecutionRequestService,
) -> None:
    case = Case.objects.create(name="回购基本价款+年化率分段", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）回购样本号",
        document_name="民事判决书",
        document_content=(
            "被告广州市花都某有限公司于本判决生效之日起十日内向原告广州市花都某有限公司支付回购基本价款2900万元及利息"
            "（以900万元为基数，自2024年9月10日起按年化率6%计算至付清之日止；"
            "以1000万元为基数，自2024年9月5日起按年化率6%计算至付清之日止；"
            "以1000万元为基数，自2024年9月14日起按年化率6%计算至付清之日止）。"
            "如果未按本判决指定的期间履行给付金钱义务，应当加倍支付迟延履行期间的债务利息。"
            "案件受理费187483.33元，由被告广州市花都某有限公司负担。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["principal"] == "29000000"
    assert params["principal_label"] == "回购基本价款"
    assert params["interest_rate_description"] == "年化率6%"
    assert params["interest_segmented"] is True
    assert len(params["interest_segments"]) == 3
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert "回购基本价款29000000元" in preview
    assert "利息（以900万元为基数" in preview
    assert "按年化率6%计算至付清之日止" in preview
    assert "暂计至2026年3月23日利息为" in preview
    assert any("受理费187483.33元已排除" in w for w in warnings)


@pytest.mark.django_db
def test_execution_request_includes_confirmed_interest_with_wei_form(service: ExecutionRequestService) -> None:
    case = Case.objects.create(name="利息为X元写法识别", target_amount=Decimal("0"))
    case_number = CaseNumber.objects.create(
        case=case,
        number="（2026）借款利息样本号",
        document_name="民事判决书",
        document_content=(
            "被告廖某应于本判决发生法律效力之日起十五日内向原告石某偿还借款本金14954607.84元及借款利息"
            "（截止至2024年4月19日，借款利息为3499242.86元；自2024年4月20日起，借款利息以14954607.84元为基数按照年利率13.8%计算至借款本金清偿之日止）。"
            "如果未按本判决指定的期间履行给付金钱义务，应当加倍支付迟延履行期间的债务利息。"
            "案件受理费138850元、财产保全费5000元，由被告廖某负担。"
        ),
        execution_cutoff_date=date(2026, 3, 23),
        execution_year_days=360,
        execution_date_inclusion="both",
    )

    result = service.preview_for_case_number(case=case, case_number=case_number, enable_llm_fallback=False)
    params = result["structured_params"]
    preview = result["preview_text"]
    warnings = result["warnings"]

    assert params["principal"] == "14954607.84"
    assert params["confirmed_interest"] == "3499242.86"
    assert params["interest_rate_description"] == "年利率13.8%"
    assert params["interest_start_date"] == "2024-04-20"
    assert Decimal(params["overdue_interest"]) > Decimal("0")
    assert "利息3499242.86元" in preview
    assert any("受理费138850元已排除" in w for w in warnings)
    assert any("财产保全费5000元已排除" in w for w in warnings)
