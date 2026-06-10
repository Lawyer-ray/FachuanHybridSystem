"""SMS 解析子模块测试 - 下载链接提取、当事人候选提取。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.automation.services.sms.parsing.download_link_extractor import DownloadLinkExtractor
from apps.automation.services.sms.parsing.party_candidate_extractor import PartyCandidateExtractor


class TestDownloadLinkExtractor:
    """测试 DownloadLinkExtractor。"""

    def setup_method(self) -> None:
        self.extractor = DownloadLinkExtractor()

    def test_empty_content(self) -> None:
        assert self.extractor.extract("") == []

    def test_no_links(self) -> None:
        assert self.extractor.extract("普通短信内容") == []

    def test_zxfw_link(self) -> None:
        content = "请点击 https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2&sdsin=3"
        links = self.extractor.extract(content)
        assert len(links) == 1
        assert "qdbh=1" in links[0]

    def test_gdems_link(self) -> None:
        content = "请查收 https://sd.gdcourts.gov.cn/v3/dzsd/ABC123"
        links = self.extractor.extract(content)
        assert len(links) == 1

    def test_jysd_link(self) -> None:
        content = "请查收 https://sd.court.gov.cn/sd?key=abc123"
        links = self.extractor.extract(content)
        assert len(links) == 1

    def test_hbfy_public_link(self) -> None:
        content = "请查收 https://hbfy.court.gov.cn/hb/msg?msg=ABC123"
        links = self.extractor.extract(content)
        assert len(links) == 1

    def test_hbfy_account_link(self) -> None:
        content = "请登录 https://hbfy.court.gov.cn/sfsddz"
        links = self.extractor.extract(content)
        assert len(links) == 1

    def test_sfdw_link(self) -> None:
        content = "请查收 https://sfsdw.court.gov.cn/sfsdw//r/ABC123"
        links = self.extractor.extract(content)
        assert len(links) == 1

    def test_multiple_different_links(self) -> None:
        content = (
            "链接1: https://sd.gdcourts.gov.cn/v3/dzsd/AAA "
            "链接2: https://sfsdw.court.gov.cn/sfsdw//r/BBB"
        )
        links = self.extractor.extract(content)
        assert len(links) == 2

    def test_duplicate_links_deduped(self) -> None:
        link = "https://sd.gdcourts.gov.cn/v3/dzsd/ABC"
        content = f"{link} {link}"
        links = self.extractor.extract(content)
        assert len(links) == 1

    def test_sanitize_trailing_punctuation(self) -> None:
        result = self.extractor._sanitize_link("https://example.com,")
        assert result == "https://example.com"

    def test_sanitize_trailing_chinese_period(self) -> None:
        result = self.extractor._sanitize_link("https://example.com。")
        assert result == "https://example.com"

    def test_is_valid_zxfw_with_all_params(self) -> None:
        link = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2&sdsin=3"
        assert self.extractor._is_valid(link) is True

    def test_is_valid_zxfw_missing_params(self) -> None:
        link = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1"
        assert self.extractor._is_valid(link) is False

    def test_is_valid_gdems(self) -> None:
        assert self.extractor._is_valid("https://sd.gdcourts.gov.cn/v3/dzsd/ABC") is True

    def test_is_valid_jysd(self) -> None:
        assert self.extractor._is_valid("https://sd.court.gov.cn/sd?key=abc") is True

    def test_is_valid_jysd_no_key(self) -> None:
        assert self.extractor._is_valid("https://sd.court.gov.cn/sd") is False

    def test_is_valid_hbfy_public(self) -> None:
        assert self.extractor._is_valid("https://hbfy.court.gov.cn/hb/msg?msg=ABC") is True

    def test_is_valid_hbfy_account(self) -> None:
        assert self.extractor._is_valid("https://hbfy.court.gov.cn/sfsddz") is True

    def test_is_valid_sfdw(self) -> None:
        assert self.extractor._is_valid("https://sfsdw.court.gov.cn/sfsdw//r/ABC") is True

    def test_is_valid_random_url(self) -> None:
        assert self.extractor._is_valid("https://example.com/random") is False


class TestPartyCandidateExtractor:
    """测试 PartyCandidateExtractor。"""

    def setup_method(self) -> None:
        self.extractor = PartyCandidateExtractor()

    def test_empty_content(self) -> None:
        assert self.extractor.extract("") == []

    def test_extract_receiver_name(self) -> None:
        content = "【佛山禅城法院】张三,你好"
        candidates = self.extractor.extract(content)
        assert "张三" in candidates

    def test_extract_company_name(self) -> None:
        content = "佛山市某某有限公司与张三合同纠纷"
        candidates = self.extractor.extract(content)
        assert any("有限公司" in c for c in candidates)

    def test_stopwords_filtered(self) -> None:
        """停用词被过滤。"""
        content = "人民法院通知你"
        result = self.extractor._clean("人民法院")
        assert result == ""

    def test_short_name_filtered(self) -> None:
        result = self.extractor._clean("张")
        assert result == ""

    def test_valid_name(self) -> None:
        result = self.extractor._clean("张三")
        assert result == "张三"

    def test_deduplicate(self) -> None:
        result = self.extractor._deduplicate(["张三", "李四", "张三", "王五"], 10)
        assert result == ["张三", "李四", "王五"]

    def test_deduplicate_max_count(self) -> None:
        result = self.extractor._deduplicate(["张三", "李四", "王五"], 2)
        assert len(result) == 2

    def test_extract_chinese_tokens(self) -> None:
        tokens = self.extractor._extract_chinese_tokens("张三李四王五赵六", 5)
        assert len(tokens) > 0

    def test_max_candidates_limit(self) -> None:
        """候选数量受 max_candidates 限制。"""
        content = "张三李四王五赵六钱七孙八周九吴十郑十一冯十二陈十三"
        candidates = self.extractor.extract(content, max_candidates=3)
        assert len(candidates) <= 3

    def test_extract_receiver_multiple(self) -> None:
        content = "【法院】张三,你好"
        candidates = self.extractor._extract_receiver_names(content)
        assert len(candidates) >= 1

    def test_clean_none_input(self) -> None:
        result = self.extractor._clean(None)  # type: ignore[arg-type]
        assert result == ""

    def test_clean_empty_string(self) -> None:
        result = self.extractor._clean("")
        assert result == ""
