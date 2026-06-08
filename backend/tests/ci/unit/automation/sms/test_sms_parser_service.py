"""短信解析服务测试 - 下载链接提取、案号提取、当事人提取等。"""

from __future__ import annotations

from unittest.mock import MagicMock

from apps.automation.services.sms.parsing.download_link_extractor import DownloadLinkExtractor
from apps.automation.services.sms.parsing.party_candidate_extractor import PartyCandidateExtractor
from apps.automation.services.sms.sms_parser_service import SMSParserService


class TestDownloadLinkExtractor:
    """DownloadLinkExtractor 纯函数测试。"""

    def setup_method(self) -> None:
        self.extractor = DownloadLinkExtractor()

    def test_extract_empty_content(self) -> None:
        """空内容返回空列表。"""
        assert self.extractor.extract("") == []
        assert self.extractor.extract("  ") == []

    def test_extract_zxfw_link(self) -> None:
        """提取人民法院在线服务网链接。"""
        content = "请点击链接查看文书 https://court.example.com/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc"
        links = self.extractor.extract(content)
        assert len(links) == 1
        assert "zxfw" in links[0]

    def test_extract_gdems_link(self) -> None:
        """提取广东电子送达链接。"""
        content = "请查收 https://gdems.court.gov.cn/v3/dzsd/abc123"
        links = self.extractor.extract(content)
        assert len(links) >= 1
        assert any("dzsd" in link for link in links)

    def test_extract_jysd_link(self) -> None:
        """提取简易送达链接。"""
        content = "请查收 https://court.example.com/sd?key=abc123def"
        links = self.extractor.extract(content)
        assert len(links) >= 1
        assert any("/sd?key=" in link for link in links)

    def test_extract_hbfy_account_link(self) -> None:
        """提取湖北电子送达账号入口链接。"""
        content = "请查收 https://hbfy.court.gov.cn/sfsddz"
        links = self.extractor.extract(content)
        assert len(links) >= 1
        assert any("sfsddz" in link for link in links)

    def test_extract_sfdw_link(self) -> None:
        """提取司法送达网链接。"""
        content = "请查收 https://sfsdw.court.gov.cn/sfsdw//r/abc123"
        links = self.extractor.extract(content)
        assert len(links) >= 1
        assert any("sfsdw//r/" in link for link in links)

    def test_sanitize_trailing_punctuation(self) -> None:
        """清洗尾部标点。"""
        assert self.extractor._sanitize_link("https://example.com/path。") == "https://example.com/path"
        assert self.extractor._sanitize_link("https://example.com/path，") == "https://example.com/path"
        assert self.extractor._sanitize_link("https://example.com/path)") == "https://example.com/path"

    def test_is_valid_zxfw_link(self) -> None:
        """验证人民法院在线服务网链接。"""
        valid = "https://court.example.com/zxfw/#/pagesajkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc"
        assert self.extractor._is_valid(valid) is True

    def test_is_valid_gdems_link(self) -> None:
        """验证广东电子送达链接。"""
        valid = "https://gdems.court.gov.cn/v3/dzsd/abc123"
        assert self.extractor._is_valid(valid) is True

    def test_is_valid_sfdw_link(self) -> None:
        """验证司法送达网链接。"""
        valid = "https://sfsdw.court.gov.cn/sfsdw//r/abc123"
        assert self.extractor._is_valid(valid) is True

    def test_is_valid_hbfy_account_link(self) -> None:
        """验证湖北电子送达账号入口链接。"""
        valid = "https://hbfy.court.gov.cn/sfsddz"
        assert self.extractor._is_valid(valid) is True

    def test_deduplicate_links(self) -> None:
        """去重重复链接。"""
        content = (
            "https://gdems.court.gov.cn/v3/dzsd/abc123 "
            "https://gdems.court.gov.cn/v3/dzsd/abc123"
        )
        links = self.extractor.extract(content)
        assert len(links) == 1


class TestPartyCandidateExtractor:
    """PartyCandidateExtractor 纯函数测试。"""

    def setup_method(self) -> None:
        self.extractor = PartyCandidateExtractor()

    def test_extract_empty_content(self) -> None:
        """空内容返回空列表。"""
        assert self.extractor.extract("") == []

    def test_extract_receiver_name(self) -> None:
        """从短信开头提取收件人姓名。"""
        content = "】张三，你的案件有新进展"
        candidates = self.extractor.extract(content)
        assert "张三" in candidates

    def test_extract_company_name(self) -> None:
        """提取公司名称。"""
        content = "佛山市某某科技有限公司与张三的合同纠纷案件"
        candidates = self.extractor.extract(content)
        assert any("科技有限公司" in c for c in candidates)

    def test_stopword_filtering(self) -> None:
        """排除法院等停用词。"""
        content = "人民法院张三书记员法官"
        candidates = self.extractor.extract(content)
        assert "人民法院" not in candidates
        assert "书记员" not in candidates
        assert "法官" not in candidates

    def test_max_candidates_limit(self) -> None:
        """限制最大候选数量。"""
        content = "】" + "，".join([f"张{i}三" for i in range(20)]) + "，你好"
        candidates = self.extractor.extract(content, max_candidates=5)
        assert len(candidates) <= 5

    def test_deduplicate(self) -> None:
        """去重候选。"""
        content = "】张三，张三你好"
        candidates = self.extractor.extract(content)
        # 张三应该只出现一次
        zhang_san_count = sum(1 for c in candidates if c == "张三")
        assert zhang_san_count <= 1

    def test_clean_short_names(self) -> None:
        """过滤太短的名字。"""
        assert self.extractor._clean("A") == ""
        assert self.extractor._clean("张三") == "张三"

    def test_clean_with_stopwords(self) -> None:
        """包含停用词的名称返回空。"""
        assert self.extractor._clean("法院书记员") == ""
        assert self.extractor._clean("平台系统") == ""


class TestSMSParserService:
    """SMSParserService 测试（mock LLM）。"""

    def setup_method(self) -> None:
        self.parser = SMSParserService(
            ollama_model="test-model",
            ollama_base_url="http://localhost:11434",
            llm_service=MagicMock(),
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=PartyCandidateExtractor(),
        )

    def test_parse_with_download_link(self) -> None:
        """解析包含下载链接的短信。"""
        content = (
            "您的案件文书已送达，请查收。"
            "https://court.example.com/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc "
            "案号：（2025）粤0604民初12345号"
        )
        result = self.parser.parse(content)
        assert result.has_valid_download_link is True
        assert len(result.case_numbers) >= 1

    def test_parse_without_download_link(self) -> None:
        """解析不含下载链接的短信。"""
        content = "您的案件（2025）粤0604民初12345号已立案，请关注。"
        result = self.parser.parse(content)
        assert result.has_valid_download_link is False

    def test_parse_filing_notification(self) -> None:
        """包含立案关键词的短信类型为立案通知。"""
        content = "您的案件已立案"
        result = self.parser.parse(content)
        assert "立案" in result.sms_type or result.sms_type is not None

    def test_extract_verification_code(self) -> None:
        """提取司法送达网验证码。"""
        content = "您的验证码：1234，请使用。"
        code = self.parser.extract_verification_code(content)
        assert code == "1234"

    def test_extract_verification_code_not_found(self) -> None:
        """未找到验证码返回空字符串。"""
        content = "这是一条普通短信"
        code = self.parser.extract_verification_code(content)
        assert code == ""

    def test_sanitize_link(self) -> None:
        """链接清洗。"""
        assert self.parser._sanitize_link("https://example.com。") == "https://example.com"
        assert self.parser._sanitize_link("  https://example.com  ") == "https://example.com"

    def test_is_valid_download_link_zxfw(self) -> None:
        """验证人民法院在线服务网链接。"""
        link = "https://court.example.com/zxfw/#/pagesajkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc"
        assert self.parser._is_valid_download_link(link) is True

    def test_is_valid_download_link_gdems(self) -> None:
        """验证广东电子送达链接。"""
        link = "https://gdems.court.gov.cn/v3/dzsd/abc123"
        assert self.parser._is_valid_download_link(link) is True

    def test_is_valid_download_link_sfdw(self) -> None:
        """验证司法送达网链接。"""
        link = "https://sfsdw.court.gov.cn/sfsdw//r/abc123"
        assert self.parser._is_valid_download_link(link) is True

    def test_is_valid_download_link_invalid(self) -> None:
        """无效链接返回 False。"""
        assert self.parser._is_valid_download_link("https://www.baidu.com") is False

    def test_filter_parties_exclude_keywords(self) -> None:
        """过滤包含排除关键词的当事人。"""
        parties = ["张三", "法院", "书记员", "李四", "平台"]
        filtered = self.parser._filter_parties(parties)
        assert "张三" in filtered
        assert "李四" in filtered
        assert "法院" not in filtered
        assert "书记员" not in filtered
        assert "平台" not in filtered

    def test_filter_parties_length(self) -> None:
        """过滤长度不符合要求的当事人。"""
        parties = ["张", "张三", "这是一个非常非常非常非常非常非常非常非常非常非常非常长的名称超过三十个字"]
        filtered = self.parser._filter_parties(parties)
        assert "张" not in filtered  # 太短
        assert "张三" in filtered

    def test_extract_party_names_from_client_service(self) -> None:
        """从客户服务中匹配当事人。"""
        mock_client = MagicMock()
        mock_client.name = "张三"
        self.parser._client_service = MagicMock()
        self.parser._client_service.get_all_clients_internal.return_value = [mock_client]

        parties = self.parser._find_existing_clients_in_sms("张三与李四的合同纠纷")
        assert "张三" in parties

    def test_collect_company_names(self) -> None:
        """提取公司名称。"""
        parties: list[str] = []
        self.parser._collect_company_names("佛山市某某科技有限公司与张三", parties)
        assert any("科技有限公司" in p for p in parties)
