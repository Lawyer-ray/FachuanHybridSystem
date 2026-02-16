from unittest.mock import Mock

from apps.documents.services.placeholders.lawyer.lawyer_info_service import LawyerInfoService
from apps.documents.services.generation.contract_generation_service import ContractDataWrapper


class TestLawyerNamesPlaceholder:
    def test_single_lawyer(self):
        service = LawyerInfoService()

        assignments = [Mock(is_primary=True, lawyer=Mock(real_name="张三", username="zhangsan"))]

        result = service.format_lawyer_names(assignments)
        assert result == "张三"

    def test_multiple_lawyers_with_primary(self):
        service = LawyerInfoService()

        assignments = [
            Mock(is_primary=False, lawyer=Mock(real_name="李四", username="lisi")),
            Mock(is_primary=True, lawyer=Mock(real_name="张三", username="zhangsan")),
            Mock(is_primary=False, lawyer=Mock(real_name="王五", username="wangwu")),
        ]

        result = service.format_lawyer_names(assignments)
        assert result == "张三、李四、王五"

    def test_multiple_primary_lawyers(self):
        service = LawyerInfoService()

        assignments = [
            Mock(is_primary=True, lawyer=Mock(real_name="张三", username="zhangsan")),
            Mock(is_primary=True, lawyer=Mock(real_name="李四", username="lisi")),
            Mock(is_primary=False, lawyer=Mock(real_name="王五", username="wangwu")),
        ]

        result = service.format_lawyer_names(assignments)
        assert result == "张三、李四、王五"

    def test_multiple_lawyers_no_primary(self):
        service = LawyerInfoService()

        assignments = [
            Mock(is_primary=False, lawyer=Mock(real_name="张三", username="zhangsan")),
            Mock(is_primary=False, lawyer=Mock(real_name="李四", username="lisi")),
        ]

        result = service.format_lawyer_names(assignments)
        assert result == "张三、李四"

    def test_with_contract_data_wrapper(self):
        service = LawyerInfoService()

        contract_data = {
            "id": 1,
            "name": "测试合同",
            "assignments": [
                {"id": 1, "lawyer_id": 1, "lawyer_name": "张三", "is_primary": True, "order": 1, "law_firm_name": "测试律所"},
                {"id": 2, "lawyer_id": 2, "lawyer_name": "李四", "is_primary": False, "order": 2, "law_firm_name": "测试律所"},
                {"id": 3, "lawyer_id": 3, "lawyer_name": "王五", "is_primary": False, "order": 3, "law_firm_name": "测试律所"},
            ],
        }

        contract = ContractDataWrapper(contract_data)

        result = service.generate({"contract": contract})
        assert result["律师姓名"] == "张三、李四、王五"
        assert result["主办律师"] == "张三"
        assert result["协办律师"] == "李四、王五"
