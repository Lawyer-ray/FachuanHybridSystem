"""contact_extraction_service 单元测试 — 联系人/电话/地址提取（标签锚定正则）。"""

from __future__ import annotations

from apps.document_recognition.services.contact_extraction_service import (
    _clean_phone,
    extract_address,
    extract_contacts,
)


class TestCleanPhone:
    def test_valid_landline(self) -> None:
        assert _clean_phone("0757-81234567") == "0757-81234567"

    def test_valid_mobile(self) -> None:
        assert _clean_phone("13800138000") == "13800138000"

    def test_too_short_rejected(self) -> None:
        assert _clean_phone("123456") is None

    def test_too_long_rejected(self) -> None:
        assert _clean_phone("1234567890123456") is None

    def test_spaces_stripped(self) -> None:
        assert _clean_phone("  0757-81234567  ") == "0757-81234567"


class TestExtractAddress:
    def test_none_and_empty(self) -> None:
        assert extract_address(None) is None
        assert extract_address("") is None

    def test_no_label(self) -> None:
        assert extract_address("广东省佛山市禅城区") is None

    def test_simple_address(self) -> None:
        text = "地址：广东省佛山市禅城区岭南大道北1号。"
        assert extract_address(text) == "广东省佛山市禅城区岭南大道北1号"

    def test_stops_at_next_label(self) -> None:
        text = "地址：某某路10号 联系电话：0757-81234567"
        assert extract_address(text) == "某某路10号"

    def test_too_short_rejected(self) -> None:
        assert extract_address("地址：abc。") is None

    def test_too_long_rejected(self) -> None:
        # 超过 60 字（无句读截断）
        assert extract_address("地址：" + "长" * 61) is None


class TestExtractContacts:
    def test_none_and_empty(self) -> None:
        assert extract_contacts(None) == []
        assert extract_contacts("") == []

    def test_nothing_found(self) -> None:
        assert extract_contacts("普通正文，无任何联系信息。") == []

    def test_role_with_name_and_phone(self) -> None:
        text = "联系人：张三 联系电话：0757-81234567"
        result = extract_contacts(text)
        assert result == [{"role": "联系人", "name": "张三", "phone": "0757-81234567"}]

    def test_multiple_names_joined(self) -> None:
        text = "承办法官：李四、王五 联系电话：0757-81234567"
        result = extract_contacts(text)
        assert result[0]["name"] == "李四、王五"
        assert result[0]["role"] == "承办法官"

    def test_name_without_phone(self) -> None:
        text = "书记员：赵六。"
        result = extract_contacts(text)
        assert result == [{"role": "书记员", "name": "赵六", "phone": None}]

    def test_orphan_phone_creates_entry(self) -> None:
        text = "联系电话：13800138000"
        result = extract_contacts(text)
        assert result == [{"role": "联系电话", "name": "", "phone": "13800138000"}]

    def test_invalid_phone_not_collected(self) -> None:
        text = "联系电话：123"
        assert extract_contacts(text) == []

    def test_multiple_role_groups(self) -> None:
        text = "联系人：张三 联系电话：0757-81234567 联系人：李四 联系电话：0757-87654321"
        result = extract_contacts(text)
        assert len(result) == 2
        assert result[0]["name"] == "张三"
        assert result[1]["name"] == "李四"
        assert {r["phone"] for r in result} == {"0757-81234567", "0757-87654321"}

    def test_duplicate_entries_deduped(self) -> None:
        text = "联系人：张三 联系电话：0757-81234567 联系人：张三 联系电话：0757-81234567"
        result = extract_contacts(text)
        assert result == [{"role": "联系人", "name": "张三", "phone": "0757-81234567"}]

    def test_phone_too_far_from_name_not_paired(self) -> None:
        # 姓名与电话之间隔超过 60 字符 → 电话不再配对，成为孤立条目
        filler = "正文" * 40
        text = f"经办人：钱九 {filler} 联系电话：0757-81234567"
        result = extract_contacts(text)
        assert result[0] == {"role": "经办人", "name": "钱九", "phone": None}
        assert result[1] == {"role": "联系电话", "name": "", "phone": "0757-81234567"}

    def test_short_names_filtered_out(self) -> None:
        # 单字/超长 token 不构成姓名
        text = "联系人：A 联系电话：0757-81234567"
        result = extract_contacts(text)
        assert result == [{"role": "联系电话", "name": "", "phone": "0757-81234567"}]
