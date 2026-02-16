"""
CauseCourtDataService 单元测试
测试案由和法院数据服务的基本功能
"""
import pytest
from apps.cases.services import CauseCourtDataService
from apps.core.exceptions import ValidationException


class TestCauseCourtDataService:
    """案由法院数据服务测试"""

    def setup_method(self):
        """每个测试方法前初始化服务"""
        self.service = CauseCourtDataService()

    # ==================== 案由数据加载测试 ====================

    def test_get_causes_by_type_civil(self):
        """测试获取民事案由"""
        causes = self.service.get_causes_by_type('civil')
        assert len(causes) > 0
        assert all('name' in c and 'id' in c for c in causes)
        # 验证包含典型民事案由
        cause_names = [c['name'] for c in causes]
        assert any('纠纷' in name for name in cause_names)

    def test_get_causes_by_type_criminal(self):
        """测试获取刑事案由"""
        causes = self.service.get_causes_by_type('criminal')
        assert len(causes) > 0
        assert all('name' in c and 'id' in c for c in causes)

    def test_get_causes_by_type_administrative(self):
        """测试获取行政案由"""
        causes = self.service.get_causes_by_type('administrative')
        assert len(causes) > 0
        assert all('name' in c and 'id' in c for c in causes)

    def test_get_causes_by_type_execution(self):
        """测试获取申请执行案由（应包含所有类型）"""
        execution_causes = self.service.get_causes_by_type('execution')
        civil_causes = self.service.get_causes_by_type('civil')
        criminal_causes = self.service.get_causes_by_type('criminal')
        administrative_causes = self.service.get_causes_by_type('administrative')
        
        # 执行类型应该包含所有三种案由
        expected_count = len(civil_causes) + len(criminal_causes) + len(administrative_causes)
        assert len(execution_causes) == expected_count

    def test_get_causes_by_type_bankruptcy(self):
        """测试获取破产案由（应返回空列表）"""
        causes = self.service.get_causes_by_type('bankruptcy')
        assert causes == []

    def test_get_causes_by_type_invalid(self):
        """测试无效案件类型"""
        with pytest.raises(ValidationException) as exc_info:
            self.service.get_causes_by_type('invalid_type')
        assert exc_info.value.code == 'INVALID_CASE_TYPE'

    # ==================== 案由搜索测试 ====================

    def test_search_causes_basic(self):
        """测试基本案由搜索"""
        results = self.service.search_causes('买卖', 'civil', limit=10)
        assert len(results) > 0
        assert all('买卖' in r['name'] for r in results)

    def test_search_causes_limit(self):
        """测试搜索结果数量限制"""
        results = self.service.search_causes('纠纷', 'civil', limit=5)
        assert len(results) <= 5

    def test_search_causes_empty_query(self):
        """测试空搜索词"""
        results = self.service.search_causes('', 'civil')
        assert results == []

    def test_search_causes_whitespace_query(self):
        """测试空白搜索词"""
        results = self.service.search_causes('   ', 'civil')
        assert results == []

    def test_search_causes_no_match(self):
        """测试无匹配结果"""
        results = self.service.search_causes('不存在的案由xyz123', 'civil')
        assert results == []

    # ==================== 法院搜索测试 ====================

    def test_search_courts_basic(self):
        """测试基本法院搜索"""
        results = self.service.search_courts('人民法院', limit=10)
        assert len(results) > 0
        assert all('人民法院' in r['name'] for r in results)

    def test_search_courts_limit(self):
        """测试法院搜索结果数量限制"""
        results = self.service.search_courts('法院', limit=5)
        assert len(results) <= 5

    def test_search_courts_empty_query(self):
        """测试空搜索词"""
        results = self.service.search_courts('')
        assert results == []

    def test_search_courts_no_match(self):
        """测试无匹配结果"""
        results = self.service.search_courts('不存在的法院xyz123')
        assert results == []

    # ==================== 数据结构测试 ====================

    def test_flatten_tree_structure(self):
        """测试扁平化树形结构"""
        # 构造测试数据
        test_data = {
            'id': '1',
            'name': '根节点',
            'children': [
                {
                    'id': '2',
                    'name': '子节点1',
                    'children': [
                        {'id': '3', 'name': '孙节点1', 'children': []}
                    ]
                },
                {
                    'id': '4',
                    'name': '子节点2',
                    'children': []
                }
            ]
        }
        
        result = self.service._flatten_tree(test_data)
        
        # 应该包含所有4个节点
        assert len(result) == 4
        names = [r['name'] for r in result]
        assert '根节点' in names
        assert '子节点1' in names
        assert '子节点2' in names
        assert '孙节点1' in names

    def test_flatten_tree_empty_name(self):
        """测试扁平化时跳过空名称节点"""
        test_data = {
            'id': '1',
            'name': '',  # 空名称
            'children': [
                {'id': '2', 'name': '有效节点', 'children': []}
            ]
        }
        
        result = self.service._flatten_tree(test_data)
        
        # 只应该包含有效节点
        assert len(result) == 1
        assert result[0]['name'] == '有效节点'
