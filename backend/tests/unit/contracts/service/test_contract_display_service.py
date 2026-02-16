import unittest
from unittest.mock import MagicMock, patch

from apps.contracts.services.contract.contract_display_service import ContractDisplayService


class TestContractDisplayService(unittest.TestCase):
    def setUp(self):
        self.mock_document_service = MagicMock()
        self.mock_template_cache = MagicMock()
        self.service = ContractDisplayService(
            document_service=self.mock_document_service,
            template_cache=self.mock_template_cache,
        )
        self.mock_contract = MagicMock()
        self.mock_contract.id = 1
        self.mock_contract.case_type = "civil"

    def test_get_matched_document_template_from_cache(self):
        """测试从缓存获取文书模板"""
        self.mock_template_cache.get_document_templates.return_value = [
            {"name": "模板A", "type_display": "类型1"},
            {"name": "模板B"},
        ]

        result = self.service.get_matched_document_template(self.mock_contract)

        self.assertEqual(result, "模板A（类型1）、模板B")
        self.mock_template_cache.get_document_templates.assert_called_with("civil")
        self.mock_document_service.find_matching_contract_templates.assert_not_called()

    def test_get_matched_document_template_from_db(self):
        """测试从数据库获取文书模板并缓存"""
        self.mock_template_cache.get_document_templates.return_value = None
        templates = [{"name": "模板A"}]
        self.mock_document_service.find_matching_contract_templates.return_value = templates

        result = self.service.get_matched_document_template(self.mock_contract)

        self.assertEqual(result, "模板A")
        self.mock_document_service.find_matching_contract_templates.assert_called_with("civil")
        self.mock_template_cache.set_document_templates.assert_called_with("civil", templates)

    def test_get_matched_document_template_none(self):
        """测试无匹配模板"""
        self.mock_template_cache.get_document_templates.return_value = []

        result = self.service.get_matched_document_template(self.mock_contract)

        self.assertEqual(result, "无匹配模板")

    def test_get_matched_folder_templates_from_cache(self):
        """测试从缓存获取文件夹模板"""
        self.mock_template_cache.get_folder_templates.return_value = [
            {"name": "文件夹A"},
            {"name": "文件夹B"},
        ]

        result = self.service.get_matched_folder_templates(self.mock_contract)

        self.assertEqual(result, "文件夹A、文件夹B")
        self.mock_template_cache.get_folder_templates.assert_called_with("civil")

    def test_has_matched_templates_both_exist(self):
        """测试同时存在文件夹和文书模板"""
        self.mock_template_cache.get_template_check.return_value = {
            "has_folder": True,
            "has_document": True,
        }

        result = self.service.has_matched_templates(self.mock_contract)

        self.assertTrue(result)

    def test_has_matched_templates_partial(self):
        """测试只存在一种模板"""
        self.mock_template_cache.get_template_check.return_value = {
            "has_folder": True,
            "has_document": False,
        }

        result = self.service.has_matched_templates(self.mock_contract)

        self.assertFalse(result)

    def test_batch_get_template_info(self):
        """测试批量获取模板信息"""
        contract1 = MagicMock()
        contract1.id = 1
        contract1.case_type = "civil"

        contract2 = MagicMock()
        contract2.id = 2
        contract2.case_type = "civil"  # Same type to test caching

        contract3 = MagicMock()
        contract3.id = 3
        contract3.case_type = "criminal"

        # Mock cache behavior
        def get_doc_side_effect(case_type):
            if case_type == "civil":
                return [{"name": "民事模板"}]
            return []

        self.mock_template_cache.get_document_templates.side_effect = get_doc_side_effect
        self.mock_template_cache.get_folder_templates.return_value = []
        self.mock_template_cache.get_template_check.return_value = {}

        result = self.service.batch_get_template_info([contract1, contract2, contract3])

        self.assertEqual(len(result), 3)
        self.assertEqual(result[1]["document_template"], "民事模板")
        self.assertEqual(result[2]["document_template"], "民事模板")
        self.assertEqual(result[3]["document_template"], "无匹配模板")

        # Verify cache was called twice (once for each unique type)
        self.assertEqual(self.mock_template_cache.get_document_templates.call_count, 2)
