import pytest

from apps.cases.services.template.unified.filename import FilenameInputs, FilenamePolicy


class _FixedDateProvider:
    def __init__(self, value: str):
        self.value = value

    def today_yyyymmdd(self) -> str:
        return self.value


def test_safe_name_replaces_illegal_chars_and_whitespace():
    policy = FilenamePolicy(date_provider=_FixedDateProvider("20990101"))
    assert policy.safe_name("  A/B\\C \n\t\r D  ") == "A／B＼C D"
    assert policy.safe_name("   ") == "未命名"


def test_filename_legal_rep_certificate_uses_client_name():
    policy = FilenamePolicy(date_provider=_FixedDateProvider("20260101"))
    name = policy.build(
        inputs=FilenameInputs(
            template_name="法定代表人身份证明书",
            case_name="测试案",
            client_name="宝铭公司",
            function_code="legal_rep_certificate",
            mode=None,
            our_party_count=1,
        ),
        legal_rep_cert_code="legal_rep_certificate",
        power_of_attorney_code="power_of_attorney",
    )
    assert name == "法定代表人身份证明书（宝铭公司）V1_20260101.docx"


@pytest.mark.parametrize(
    "mode,our_party_count,expected",
    [
        ("individual", 2, "授权委托书（张三）（测试案）V1_20260101.docx"),
        ("combined", 2, "授权委托书（测试案）V1_20260101.docx"),
        ("individual", 1, "授权委托书（测试案）V1_20260101.docx"),
    ],
)
def test_filename_power_of_attorney_modes(mode, our_party_count, expected):
    policy = FilenamePolicy(date_provider=_FixedDateProvider("20260101"))
    name = policy.build(
        inputs=FilenameInputs(
            template_name="授权委托书",
            case_name="测试案",
            client_name="张三",
            function_code="power_of_attorney",
            mode=mode,
            our_party_count=our_party_count,
        ),
        legal_rep_cert_code="legal_rep_certificate",
        power_of_attorney_code="power_of_attorney",
    )
    assert name == expected


def test_filename_default_uses_case_name():
    policy = FilenamePolicy(date_provider=_FixedDateProvider("20260101"))
    name = policy.build(
        inputs=FilenameInputs(
            template_name="起诉状",
            case_name="测试案",
            client_name=None,
            function_code="whatever",
            mode=None,
            our_party_count=0,
        ),
        legal_rep_cert_code="legal_rep_certificate",
        power_of_attorney_code="power_of_attorney",
    )
    assert name == "起诉状（测试案）V1_20260101.docx"
