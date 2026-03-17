from __future__ import annotations

from apps.client.services.text_parser import parse_client_text, parse_multiple_clients_text


def test_parse_company_from_first_line_with_field_variants() -> None:
    text = """
腾讯科技（深圳）有限公司
统一社会信用代码 91440300708461136T
法定代表人 马化腾
注册地址 深圳市南山区科技园科技中一路
联系电话 0755-86013388
""".strip()

    result = parse_client_text(text)

    assert result["name"] == "腾讯科技（深圳）有限公司"
    assert result["client_type"] == "legal"
    assert result["id_number"] == "91440300708461136T"
    assert result["legal_representative"] == "马化腾"
    assert result["phone"] == "0755-86013388"
    assert result["address"] == "深圳市南山区科技园科技中一路"


def test_parse_natural_person_without_colon_role_label() -> None:
    text = """
被告 李四，男，汉族，1985年1月1日出生
身份证号 440101198501011234
电话 13800138000
住址 广州市天河区员村二横路8号
""".strip()

    result = parse_client_text(text)

    assert result["name"] == "李四"
    assert result["client_type"] == "natural"
    assert result["id_number"] == "440101198501011234"
    assert result["phone"] == "13800138000"
    assert result["address"] == "广州市天河区员村二横路8号"


def test_parse_inline_company_text_without_name_field() -> None:
    text = (
        "广州阿尔法科技有限公司 统一社会信用代码 91440101MA59A1B2C3 "
        "法定代表人 张三 联系方式 020-88886666 经营地址 广州市黄埔区科学大道88号"
    )

    result = parse_client_text(text)

    assert result["name"] == "广州阿尔法科技有限公司"
    assert result["client_type"] == "legal"
    assert result["id_number"] == "91440101MA59A1B2C3"
    assert result["legal_representative"] == "张三"
    assert result["phone"] == "020-88886666"
    assert result["address"] == "广州市黄埔区科学大道88号"


def test_parse_phone_by_fallback_pattern_without_label() -> None:
    text = "原告：王五，男，身份证号：440101198901012233，住址：广州市越秀区北京路99号，13800139000"

    result = parse_client_text(text)

    assert result["name"] == "王五"
    assert result["phone"] == "13800139000"


def test_parse_should_not_forge_name_from_identifier_lines() -> None:
    text = """
统一社会信用代码: 91440101MA59A1B2C3
电话: 020-12345678
地址: 广州市天河区珠江新城
""".strip()

    result = parse_client_text(text)

    assert result["name"] == ""
    assert result["id_number"] == "91440101MA59A1B2C3"
    assert result["phone"] == "020-12345678"
    assert result["address"] == "广州市天河区珠江新城"


def test_parse_multiple_clients_with_extended_roles() -> None:
    text = """
申请执行人：广州测试科技有限公司
统一社会信用代码：91440101MA59A1B2C3
法定代表人：张三

被执行人：李四，男
身份证号：440101198501011234
电话：13900139000
""".strip()

    results = parse_multiple_clients_text(text)

    assert len(results) == 2
    assert results[0]["name"] == "广州测试科技有限公司"
    assert results[0]["client_type"] == "legal"
    assert results[0]["id_number"] == "91440101MA59A1B2C3"
    assert results[1]["name"] == "李四"
    assert results[1]["client_type"] == "natural"
    assert results[1]["id_number"] == "440101198501011234"


def test_parse_name_field_without_colon() -> None:
    text = """
企业名称 腾讯科技（深圳）有限公司
统一社会信用代码 91440300708461136T
法定代表人 马化腾
电话 0755-86013388
""".strip()

    result = parse_client_text(text)

    assert result["name"] == "腾讯科技（深圳）有限公司"
    assert result["client_type"] == "legal"
    assert result["id_number"] == "91440300708461136T"
    assert result["legal_representative"] == "马化腾"


def test_parse_plain_person_text_without_role() -> None:
    text = "张三，身份证号440101199001011234，联系电话13800138000，住址广州市海珠区新港中路99号"

    result = parse_client_text(text)

    assert result["name"] == "张三"
    assert result["client_type"] == "natural"
    assert result["id_number"] == "440101199001011234"
    assert result["phone"] == "13800138000"
    assert result["address"] == "广州市海珠区新港中路99号"


def test_parse_numbered_roles_and_bullet_lines() -> None:
    text = """
1. 原告：广州甲公司
统一社会信用代码：91440101MA59A1B2C3

2. 被告一：李四，男
身份证号：440101198501011234

3. 被告二：王五，男
身份证号：440101198601011235
""".strip()

    results = parse_multiple_clients_text(text)

    assert len(results) == 3
    assert results[0]["name"] == "广州甲公司"
    assert results[1]["name"] == "李四"
    assert results[2]["name"] == "王五"


def test_parse_parenthesized_role_aliases_without_newlines() -> None:
    text = (
        "原告（反诉被告）：深圳市南山科技有限公司 统一社会信用代码：91440300MA5ABCDE12 "
        "法定代表人：赵六；被告（反诉原告）：陈七，身份证号：440101198701011236"
    )

    results = parse_multiple_clients_text(text)

    assert len(results) == 2
    assert results[0]["name"] == "深圳市南山科技有限公司"
    assert results[0]["client_type"] == "legal"
    assert results[1]["name"] == "陈七"
    assert results[1]["client_type"] == "natural"
