"""
案由和法院模型单元测试

测试 CauseOfAction 和 Court 模型的基本功能。
"""

import pytest
from django.db import IntegrityError

from apps.core.models import CauseOfAction, Court


@pytest.mark.django_db
class TestCauseOfActionModel:
    """CauseOfAction 模型测试"""

    def test_create_cause_of_action(self):
        """测试创建案由"""
        cause = CauseOfAction.objects.create(
            code="test001",
            name="测试案由",
            case_type=CauseOfAction.CaseType.CIVIL,
            level=1,
        )
        assert cause.id is not None
        assert cause.code == "test001"
        assert cause.name == "测试案由"
        assert cause.case_type == "civil"
        assert cause.level == 1
        assert cause.is_active is True
        assert cause.is_deprecated is False

    def test_cause_of_action_str(self):
        """测试案由字符串表示"""
        cause = CauseOfAction(
            code="test002",
            name="合同纠纷",
            case_type=CauseOfAction.CaseType.CIVIL,
        )
        assert str(cause) == "合同纠纷 (民事)"

    def test_cause_of_action_case_type_choices(self):
        """测试案件类型选项"""
        choices = CauseOfAction.CaseType.choices
        assert len(choices) == 3
        assert ("civil", "民事") in choices
        assert ("criminal", "刑事") in choices
        assert ("administrative", "行政") in choices

    def test_cause_of_action_unique_code(self):
        """测试案由编码唯一性"""
        CauseOfAction.objects.create(
            code="unique001",
            name="案由1",
            case_type=CauseOfAction.CaseType.CIVIL,
        )
        with pytest.raises(IntegrityError):
            CauseOfAction.objects.create(
                code="unique001",
                name="案由2",
                case_type=CauseOfAction.CaseType.CRIMINAL,
            )

    def test_cause_of_action_hierarchical(self):
        """测试案由层级结构"""
        parent = CauseOfAction.objects.create(
            code="parent001",
            name="父级案由",
            case_type=CauseOfAction.CaseType.CIVIL,
            level=1,
        )
        child = CauseOfAction.objects.create(
            code="child001",
            name="子级案由",
            case_type=CauseOfAction.CaseType.CIVIL,
            parent=parent,
            level=2,
        )
        assert child.parent == parent
        assert parent.children.count() == 1
        assert parent.children.first() == child

    def test_cause_of_action_full_path(self):
        """测试案由完整路径"""
        parent = CauseOfAction.objects.create(
            code="path_parent",
            name="合同纠纷",
            case_type=CauseOfAction.CaseType.CIVIL,
            level=1,
        )
        child = CauseOfAction.objects.create(
            code="path_child",
            name="买卖合同纠纷",
            case_type=CauseOfAction.CaseType.CIVIL,
            parent=parent,
            level=2,
        )
        assert child.full_path == "合同纠纷 > 买卖合同纠纷"


@pytest.mark.django_db
class TestCourtModel:
    """Court 模型测试"""

    def test_create_court(self):
        """测试创建法院"""
        court = Court.objects.create(
            code="court001",
            name="北京市高级人民法院",
            level=2,
            province="北京市",
        )
        assert court.id is not None
        assert court.code == "court001"
        assert court.name == "北京市高级人民法院"
        assert court.level == 2
        assert court.province == "北京市"
        assert court.is_active is True

    def test_court_str(self):
        """测试法院字符串表示"""
        court = Court(
            code="court002",
            name="上海市高级人民法院",
        )
        assert str(court) == "上海市高级人民法院"

    def test_court_unique_code(self):
        """测试法院编码唯一性"""
        Court.objects.create(
            code="unique_court",
            name="法院1",
        )
        with pytest.raises(IntegrityError):
            Court.objects.create(
                code="unique_court",
                name="法院2",
            )

    def test_court_hierarchical(self):
        """测试法院层级结构"""
        province = Court.objects.create(
            code="province001",
            name="北京市",
            level=1,
            province="北京市",
        )
        high_court = Court.objects.create(
            code="high001",
            name="北京市高级人民法院",
            parent=province,
            level=2,
            province="北京市",
        )
        assert high_court.parent == province
        assert province.children.count() == 1
        assert province.children.first() == high_court

    def test_court_full_path(self):
        """测试法院完整路径"""
        province = Court.objects.create(
            code="path_province",
            name="北京市",
            level=1,
            province="北京市",
        )
        court = Court.objects.create(
            code="path_court",
            name="北京市高级人民法院",
            parent=province,
            level=2,
            province="北京市",
        )
        assert court.full_path == "北京市 > 北京市高级人民法院"
