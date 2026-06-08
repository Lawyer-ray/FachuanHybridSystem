"""SMS 匹配子服务测试（DocumentParserService、PartyMatchingService）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.automation.services.sms.matching.document_parser_service import DocumentParserService
from apps.automation.services.sms.matching.party_matching_service import PartyMatchingService


class TestDocumentParserService:
    """DocumentParserService 测试。"""

    def setup_method(self) -> None:
        self.client_service = MagicMock()
        self.lawyer_service = MagicMock()
        self.service = DocumentParserService(
            client_service=self.client_service,
            lawyer_service=self.lawyer_service,
        )

    def test_match_parties_from_content_empty(self) -> None:
        """空内容返回空列表。"""
        assert self.service.match_parties_from_content("") == []

    def test_match_parties_from_content_found(self) -> None:
        """在文书中匹配到客户。"""
        mock_client = SimpleNamespace(name="张三")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = []

        result = self.service.match_parties_from_content("张三与李四的合同纠纷案件判决书")
        assert "张三" in result

    def test_match_parties_from_content_not_found(self) -> None:
        """文书中未匹配到客户。"""
        mock_client = SimpleNamespace(name="王五")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = []

        result = self.service.match_parties_from_content("张三与李四的合同纠纷")
        assert "王五" not in result

    def test_match_parties_excludes_lawyers(self) -> None:
        """排除律师姓名。"""
        mock_client = SimpleNamespace(name="张律师")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = ["张律师"]

        result = self.service.match_parties_from_content("张律师代理张三的案件")
        assert "张律师" not in result

    def test_match_parties_short_name_skipped(self) -> None:
        """太短的客户名跳过。"""
        mock_client = SimpleNamespace(name="张")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = []

        result = self.service.match_parties_from_content("张三与李四")
        assert len(result) == 0

    def test_get_lawyer_names_success(self) -> None:
        """获取律师姓名。"""
        self.lawyer_service.get_all_lawyer_names.return_value = ["张律师", "李律师"]
        result = self.service.get_lawyer_names()
        assert result == ["张律师", "李律师"]

    def test_get_lawyer_names_exception(self) -> None:
        """获取律师姓名异常返回空列表。"""
        self.lawyer_service.get_all_lawyer_names.side_effect = Exception("error")
        result = self.service.get_lawyer_names()
        assert result == []

    def test_get_all_document_paths_no_scraper_task(self) -> None:
        """无 scraper_task 返回空列表。"""
        sms = SimpleNamespace(scraper_task=None)
        result = self.service.get_all_document_paths(sms)
        assert result == []


class TestPartyMatchingService:
    """PartyMatchingService 测试。"""

    def setup_method(self) -> None:
        self.client_service = MagicMock()
        self.lawyer_service = MagicMock()
        self.service = PartyMatchingService(
            client_service=self.client_service,
            lawyer_service=self.lawyer_service,
        )

    def test_find_existing_clients_in_sms_empty(self) -> None:
        """空当事人列表返回空。"""
        assert self.service.find_existing_clients_in_sms([]) == []

    def test_find_existing_clients_exact_match(self) -> None:
        """精确匹配。"""
        mock_client = SimpleNamespace(id=1, name="张三")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = []

        result = self.service.find_existing_clients_in_sms(["张三", "李四"])
        assert len(result) == 1
        assert result[0].name == "张三"

    def test_find_existing_clients_contains_match(self) -> None:
        """包含匹配。"""
        mock_client = SimpleNamespace(id=1, name="张三")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = []

        # "张三" 包含在 "张三丰" 中
        result = self.service.find_existing_clients_in_sms(["张三丰", "李四"])
        assert len(result) == 1

    def test_find_existing_clients_exclude_lawyers(self) -> None:
        """排除律师。"""
        mock_client = SimpleNamespace(id=1, name="张律师")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = ["张律师"]

        result = self.service.find_existing_clients_in_sms(["张律师", "李四"])
        assert len(result) == 0

    def test_find_existing_clients_no_match(self) -> None:
        """无匹配。"""
        mock_client = SimpleNamespace(id=1, name="王五")
        self.client_service.get_all_clients_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = []

        result = self.service.find_existing_clients_in_sms(["张三", "李四"])
        assert len(result) == 0

    def test_extract_and_match_parties_empty(self) -> None:
        """空列表返回空。"""
        assert self.service.extract_and_match_parties_from_sms([]) == []

    def test_extract_and_match_parties_success(self) -> None:
        """模糊匹配成功。"""
        mock_client = SimpleNamespace(id=1, name="张三")
        self.client_service.search_clients_by_name_internal.return_value = [mock_client]
        self.lawyer_service.get_all_lawyer_names.return_value = []

        result = self.service.extract_and_match_parties_from_sms(["张三"])
        assert len(result) == 1

    def test_extract_and_match_parties_short_name_skipped(self) -> None:
        """太短的名字跳过。"""
        self.lawyer_service.get_all_lawyer_names.return_value = []
        result = self.service.extract_and_match_parties_from_sms(["张"])
        assert len(result) == 0

    def test_deduplicate_clients(self) -> None:
        """去重客户。"""
        clients = [
            SimpleNamespace(id=1, name="张三"),
            SimpleNamespace(id=1, name="张三"),
            SimpleNamespace(id=2, name="李四"),
        ]
        result = self.service._deduplicate_clients(clients)
        assert len(result) == 2

    def test_get_lawyer_names_success(self) -> None:
        """获取律师姓名。"""
        self.lawyer_service.get_all_lawyer_names.return_value = ["张律师"]
        result = self.service.get_lawyer_names()
        assert result == ["张律师"]

    def test_get_lawyer_names_exception(self) -> None:
        """异常返回空列表。"""
        self.lawyer_service.get_all_lawyer_names.side_effect = Exception("error")
        result = self.service.get_lawyer_names()
        assert result == []
