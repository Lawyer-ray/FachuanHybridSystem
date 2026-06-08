"""Core Model 测试 - Court, CauseOfAction, SystemConfig"""

from __future__ import annotations

from typing import Any

import pytest

from apps.core.models import CauseOfAction, Court, SystemConfig


@pytest.mark.django_db
class TestCourtModel:
    """Court 模型测试"""

    def test_create_court(self) -> None:
        """创建法院"""
        court = Court.objects.create(code="000001", name="最高人民法院", level=1, is_active=True)
        assert court.code == "000001"
        assert court.name == "最高人民法院"
        assert court.level == 1

    def test_court_hierarchy(self) -> None:
        """法院层级关系"""
        parent = Court.objects.create(code="000001", name="最高法院", level=1, is_active=True)
        child = Court.objects.create(code="110000", name="北京高院", level=2, parent=parent, is_active=True)
        assert child.parent == parent
        assert parent.children.count() == 1

    def test_court_full_path(self) -> None:
        """法院完整路径"""
        grandparent = Court.objects.create(code="000001", name="最高法院", level=1, is_active=True)
        parent = Court.objects.create(code="110000", name="北京高院", level=2, parent=grandparent, is_active=True)
        child = Court.objects.create(code="110100", name="北京一中院", level=3, parent=parent, is_active=True)
        # full_path 应包含所有层级
        assert "最高法院" in child.full_path
        assert "北京高院" in child.full_path
        assert "北京一中院" in child.full_path

    def test_court_is_active(self) -> None:
        """法院激活状态"""
        court = Court.objects.create(code="000002", name="禁用法院", level=1, is_active=False)
        assert court.is_active is False


@pytest.mark.django_db
class TestCauseOfActionModel:
    """CauseOfAction 模型测试"""

    def test_create_cause(self) -> None:
        """创建案由"""
        cause = CauseOfAction.objects.create(
            code="01", name="一级案由", case_type="civil", level=1, is_active=True
        )
        assert cause.code == "01"
        assert cause.name == "一级案由"
        assert cause.case_type == "civil"

    def test_cause_hierarchy(self) -> None:
        """案由层级关系"""
        parent = CauseOfAction.objects.create(
            code="01", name="一级案由", case_type="civil", level=1, is_active=True
        )
        child = CauseOfAction.objects.create(
            code="0101", name="二级案由", case_type="civil", level=2, parent=parent, is_active=True
        )
        assert child.parent == parent
        assert parent.children.count() == 1

    def test_cause_full_path(self) -> None:
        """案由完整路径"""
        grandparent = CauseOfAction.objects.create(
            code="01", name="一级案由", case_type="civil", level=1, is_active=True
        )
        parent = CauseOfAction.objects.create(
            code="0101", name="二级案由", case_type="civil", level=2, parent=grandparent, is_active=True
        )
        child = CauseOfAction.objects.create(
            code="010101", name="三级案由", case_type="civil", level=3, parent=parent, is_active=True
        )
        assert "一级案由" in child.full_path
        assert "二级案由" in child.full_path
        assert "三级案由" in child.full_path

    def test_cause_deprecated(self) -> None:
        """案由废弃状态"""
        cause = CauseOfAction.objects.create(
            code="02", name="废弃案由", case_type="civil", level=1, is_active=True, is_deprecated=True
        )
        assert cause.is_deprecated is True

    def test_cause_type_choices(self) -> None:
        """案由类型选项"""
        civil = CauseOfAction.objects.create(
            code="C01", name="民事案由", case_type="civil", level=1, is_active=True
        )
        criminal = CauseOfAction.objects.create(
            code="X01", name="刑事案由", case_type="criminal", level=1, is_active=True
        )
        admin = CauseOfAction.objects.create(
            code="A01", name="行政案由", case_type="administrative", level=1, is_active=True
        )
        assert civil.case_type == "civil"
        assert criminal.case_type == "criminal"
        assert admin.case_type == "administrative"


@pytest.mark.django_db
class TestSystemConfigModel:
    """SystemConfig 模型测试"""

    def test_create_config(self) -> None:
        """创建系统配置"""
        config = SystemConfig.objects.create(
            key="test_key", value="test_value", category="general", description="测试配置"
        )
        assert config.key == "test_key"
        assert config.value == "test_value"
        assert config.category == "general"

    def test_config_secret(self) -> None:
        """密钥配置"""
        config = SystemConfig.objects.create(
            key="secret_key", value="secret_value", category="general", description="密钥配置", is_secret=True
        )
        assert config.is_secret is True

    def test_config_active(self) -> None:
        """配置激活状态"""
        config = SystemConfig.objects.create(
            key="active_key", value="active_value", category="general", description="激活配置", is_active=True
        )
        assert config.is_active is True

    def test_config_category_choices(self) -> None:
        """配置分类选项"""
        # 测试主要分类
        categories = ["general", "feishu", "dingtalk", "wechat_work", "telegram", "court_sms", "ai", "llm"]
        for cat in categories:
            config = SystemConfig.objects.create(
                key=f"cat_{cat}", value=f"value_{cat}", category=cat, description=f"{cat}配置"
            )
            assert config.category == cat
