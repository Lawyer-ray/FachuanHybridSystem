"""
法院 API 客户端单元测试

测试 CourtApiClient 的响应解析逻辑。
"""

import pytest

from apps.core.services.court_api_client import CourtApiClient, CauseItem, CourtItem


class TestCourtApiClientParsing:
    """CourtApiClient 解析测试"""

    def setup_method(self):
        """测试前初始化"""
        self.client = CourtApiClient()

    def test_parse_cause_response_basic(self):
        """测试基本案由响应解析"""
        # 新的响应格式：{"code": 200, "data": {"code": 200, "data": {"lbs": [...]}}}
        response = {
            "code": 200,
            "data": {
                "code": 200,
                "data": {
                    "0300": [
                        {
                            "id": "wrap",
                            "name": "民事案由",
                            "children": [{"id": "1001", "name": "合同纠纷", "children": []}],
                        }
                    ],
                }
            },
        }
        causes = self.client.parse_cause_response(response, "0300", "civil")
        assert len(causes) == 1
        assert causes[0].case_type == "civil"
        assert causes[0].code == "1001"
        assert causes[0].name == "合同纠纷"

    def test_parse_cause_response_hierarchical(self):
        """测试层级案由响应解析"""
        response = {
            "code": 200,
            "data": {
                "code": 200,
                "data": {
                    "0300": [
                        {
                            "id": "2001",
                            "name": "合同纠纷",
                            "children": [
                                {
                                    "id": "2001001",
                                    "name": "买卖合同纠纷",
                                    "children": [],
                                }
                            ],
                        }
                    ]
                }
            },
        }
        causes = self.client.parse_cause_response(response, "0300", "civil")
        assert len(causes) == 1

        parent = causes[0]
        assert parent.code == "2001"
        assert parent.name == "合同纠纷"
        assert parent.level == 1
        assert len(parent.children) == 1

        child = parent.children[0]
        assert child.code == "2001001"
        assert child.name == "买卖合同纠纷"
        assert child.level == 2
        assert child.parent_code == "2001"

    def test_parse_cause_response_empty(self):
        """测试空案由响应解析"""
        response = {"code": 200, "data": {"code": 200, "data": {"0300": []}}}
        causes = self.client.parse_cause_response(response, "0300", "civil")
        assert len(causes) == 0

    def test_parse_cause_response_missing_data(self):
        """测试缺少 data 字段"""
        response = {"code": 200, "data": {"code": 200, "data": {}}}
        causes = self.client.parse_cause_response(response, "0300", "civil")
        assert len(causes) == 0

    def test_parse_court_response_basic(self):
        """测试基本法院响应解析"""
        response = {
            "code": 200,
            "data": [
                {"id": "110000", "name": "北京市", "cGbm": "110000", "children": []},
                {"id": "310000", "name": "上海市", "cGbm": "310000", "children": []},
            ],
        }
        courts = self.client.parse_court_response(response)
        assert len(courts) == 2

        # 验证省份设置
        assert courts[0].province == "北京市"
        assert courts[1].province == "上海市"

    def test_parse_court_response_hierarchical(self):
        """测试层级法院响应解析"""
        response = {
            "code": 200,
            "data": [
                {
                    "id": "110000",
                    "name": "北京市",
                    "cGbm": "110000",
                    "children": [
                        {
                            "id": "110100",
                            "name": "北京市高级人民法院",
                            "cGbm": "110100",
                            "children": [],
                        }
                    ],
                }
            ],
        }
        courts = self.client.parse_court_response(response)
        assert len(courts) == 1

        province = courts[0]
        assert province.code == "110000"
        assert province.name == "北京市"
        assert province.level == 1
        assert province.province == "北京市"
        assert len(province.children) == 1

        court = province.children[0]
        assert court.code == "110100"
        assert court.name == "北京市高级人民法院"
        assert court.level == 2
        assert court.province == "北京市"  # 继承省份
        assert court.parent_code == "110000"

    def test_parse_court_response_empty(self):
        """测试空法院响应解析"""
        response = {"code": 200, "data": []}
        courts = self.client.parse_court_response(response)
        assert len(courts) == 0

    def test_parse_court_response_use_cGbm_as_code(self):
        """测试优先使用 cGbm 作为编码"""
        response = {
            "code": 200,
            "data": [
                {"id": "old_id", "name": "测试法院", "cGbm": "new_code", "children": []}
            ],
        }
        courts = self.client.parse_court_response(response)
        assert courts[0].code == "new_code"

    def test_parse_court_response_fallback_to_id(self):
        """测试回退到 id 作为编码"""
        response = {
            "code": 200,
            "data": [{"id": "fallback_id", "name": "测试法院", "children": []}],
        }
        courts = self.client.parse_court_response(response)
        assert courts[0].code == "fallback_id"


class TestCourtApiClientValidation:
    """CourtApiClient 验证测试"""

    def setup_method(self):
        """测试前初始化"""
        self.client = CourtApiClient()

    def test_is_valid_response_success(self):
        """测试有效响应验证"""
        assert self.client._is_valid_response({"code": 200}) is True
        assert self.client._is_valid_response({"code": "200"}) is True

    def test_is_valid_response_failure(self):
        """测试无效响应验证"""
        assert self.client._is_valid_response({"code": 400}) is False
        assert self.client._is_valid_response({"code": 500}) is False
        assert self.client._is_valid_response({}) is False
        assert self.client._is_valid_response("not a dict") is False

    def test_lbs_type_map(self):
        """测试 lbs 参数到案件类型的映射"""
        assert CourtApiClient.LBS_TYPE_MAP == {
            "0200": "criminal",
            "0300": "civil",
            "0400": "administrative",
        }
