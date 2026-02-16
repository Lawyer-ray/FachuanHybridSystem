"""
CourtSMSRepository 单元测试
"""

from unittest.mock import Mock

import pytest

from apps.automation.models import CourtSMS
from apps.automation.services.sms.court_sms_repository import CourtSMSRepository
from apps.core.exceptions import NotFoundError


@pytest.mark.django_db
class TestCourtSMSRepository:
    """短信仓储服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.repository = CourtSMSRepository()

    def test_get_by_id_success(self):
        """测试根据 ID 获取短信成功"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试短信内容", status="pending")

        # 执行测试
        result = self.repository.get_by_id(sms_id=sms.id)

        # 断言结果
        assert result.id == sms.id
        assert result.phone_number == "13800138000"
        assert result.content == "测试短信内容"
        assert result.status == "pending"

    def test_get_by_id_not_found(self):
        """测试获取不存在的短信抛出异常"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.repository.get_by_id(sms_id=999)

        assert "短信记录不存在" in str(exc_info.value.message)
        assert "ID=999" in str(exc_info.value.message)

    def test_save_success(self):
        """测试保存短信成功"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="原内容", status="pending")

        # 修改短信
        sms.content = "新内容"
        sms.status = "processed"

        # 执行测试
        self.repository.save(sms=sms)

        # 验证数据库
        sms.refresh_from_db()
        assert sms.content == "新内容"
        assert sms.status == "processed"

    def test_refresh_success(self):
        """测试刷新短信数据成功"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="原内容", status="pending")

        # 直接在数据库中修改
        CourtSMS.objects.filter(id=sms.id).update(content="数据库中的新内容")

        # 执行测试
        refreshed_sms = self.repository.refresh(sms=sms)

        # 断言结果
        assert refreshed_sms.content == "数据库中的新内容"
        assert refreshed_sms.id == sms.id

    def test_set_error_success(self):
        """测试设置错误信息成功"""
        # 创建测试短信
        sms = CourtSMS.objects.create(
            phone_number="13800138000", content="测试内容", status="pending", error_message=None
        )

        # 执行测试
        self.repository.set_error(sms=sms, message="处理失败：网络错误")

        # 验证数据库
        sms.refresh_from_db()
        assert sms.error_message == "处理失败：网络错误"

    def test_set_error_updates_timestamp(self):
        """测试设置错误信息会更新时间戳"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")
        original_updated_at = sms.updated_at

        # 执行测试
        self.repository.set_error(sms=sms, message="错误信息")

        # 验证时间戳更新
        sms.refresh_from_db()
        assert sms.updated_at > original_updated_at

    def test_clear_error_success(self):
        """测试清除错误信息成功"""
        # 创建带错误信息的测试短信
        sms = CourtSMS.objects.create(
            phone_number="13800138000", content="测试内容", status="error", error_message="之前的错误"
        )

        # 执行测试
        self.repository.clear_error(sms=sms)

        # 验证数据库
        sms.refresh_from_db()
        assert sms.error_message is None

    def test_reset_retry_fields_success(self):
        """测试重置重试字段成功"""
        # 创建测试短信（带有关联数据）
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="error")
        # 设置一些字段值
        sms.scraper_task = "task_123"
        sms.case_id = 1
        sms.case_log_id = 2
        sms.feishu_sent_at = "2024-01-01 10:00:00"
        sms.feishu_error = "发送失败"
        sms.save()

        # 执行测试
        self.repository.reset_retry_fields(sms=sms)

        # 验证字段被重置
        assert sms.scraper_task is None
        assert sms.case is None
        assert sms.case_log is None
        assert sms.feishu_sent_at is None
        assert sms.feishu_error is None

    def test_set_status_success(self):
        """测试设置状态成功"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")

        # 执行测试
        self.repository.set_status(sms=sms, status="processed")

        # 验证数据库
        sms.refresh_from_db()
        assert sms.status == "processed"
        assert sms.error_message is None

    def test_set_status_with_error_message(self):
        """测试设置状态并附带错误信息"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")

        # 执行测试
        self.repository.set_status(sms=sms, status="error", error_message="处理失败")

        # 验证数据库
        sms.refresh_from_db()
        assert sms.status == "error"
        assert sms.error_message == "处理失败"

    def test_set_status_clear_error_message(self):
        """测试设置状态可以清除错误信息"""
        # 创建带错误的测试短信
        sms = CourtSMS.objects.create(
            phone_number="13800138000", content="测试内容", status="error", error_message="之前的错误"
        )

        # 执行测试 - 设置为成功状态，不传错误信息
        self.repository.set_status(sms=sms, status="processed", error_message=None)

        # 验证数据库
        sms.refresh_from_db()
        assert sms.status == "processed"
        assert sms.error_message is None


@pytest.mark.django_db
class TestCourtSMSRepositoryEdgeCases:
    """短信仓储服务边界情况测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.repository = CourtSMSRepository()

    def test_save_partial_update(self):
        """测试保存时只更新特定字段"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="原内容", status="pending")

        # 修改多个字段
        sms.content = "新内容"
        sms.status = "processed"

        # 执行测试 - save 方法会保存所有字段
        self.repository.save(sms=sms)

        # 验证数据库
        sms.refresh_from_db()
        assert sms.content == "新内容"
        assert sms.status == "processed"

    def test_set_error_with_long_message(self):
        """测试设置长错误信息"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")

        # 执行测试 - 设置很长的错误信息
        long_message = "错误" * 500
        self.repository.set_error(sms=sms, message=long_message)

        # 验证数据库
        sms.refresh_from_db()
        assert sms.error_message == long_message

    def test_set_error_with_empty_message(self):
        """测试设置空错误信息"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")

        # 执行测试
        self.repository.set_error(sms=sms, message="")

        # 验证数据库
        sms.refresh_from_db()
        assert sms.error_message == ""

    def test_reset_retry_fields_already_none(self):
        """测试重置已经为 None 的字段"""
        # 创建测试短信（字段已经是 None）
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")

        # 执行测试 - 不应该抛出异常
        self.repository.reset_retry_fields(sms=sms)

        # 验证字段仍然是 None
        assert sms.scraper_task is None
        assert sms.case is None
        assert sms.case_log is None

    def test_set_status_multiple_times(self):
        """测试多次设置状态"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")

        # 第一次设置
        self.repository.set_status(sms=sms, status="processing")
        sms.refresh_from_db()
        assert sms.status == "processing"

        # 第二次设置
        self.repository.set_status(sms=sms, status="processed")
        sms.refresh_from_db()
        assert sms.status == "processed"

        # 第三次设置（带错误）
        self.repository.set_status(sms=sms, status="error", error_message="失败")
        sms.refresh_from_db()
        assert sms.status == "error"
        assert sms.error_message == "失败"

    def test_refresh_after_external_modification(self):
        """测试外部修改后刷新"""
        # 创建测试短信
        sms = CourtSMS.objects.create(phone_number="13800138000", content="原内容", status="pending")

        # 模拟外部修改（直接更新数据库）
        CourtSMS.objects.filter(id=sms.id).update(content="外部修改的内容", status="external_status")

        # 执行测试
        refreshed_sms = self.repository.refresh(sms=sms)

        # 断言结果
        assert refreshed_sms.content == "外部修改的内容"
        assert refreshed_sms.status == "external_status"

    def test_get_by_id_with_related_data(self):
        """测试获取带关联数据的短信"""
        # 创建测试短信（可能有外键关联）
        sms = CourtSMS.objects.create(phone_number="13800138000", content="测试内容", status="pending")

        # 执行测试
        result = self.repository.get_by_id(sms_id=sms.id)

        # 断言结果
        assert result.id == sms.id
        # 验证可以访问关联字段（即使为 None）
        assert result.case is None
        assert result.case_log is None
