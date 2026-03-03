"""
CourtSMSRepository 单元测试
"""

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS
from apps.automation.services.sms.court_sms_repository import CourtSMSRepository
from apps.core.exceptions import NotFoundError


def _make_sms(**kwargs: object) -> CourtSMS:
    """创建测试用 CourtSMS，自动填充必填字段"""
    defaults: dict[str, object] = {
        "content": "测试短信内容",
        "received_at": timezone.now(),
        "status": "pending",
    }
    defaults.update(kwargs)
    return CourtSMS.objects.create(**defaults)


@pytest.mark.django_db
class TestCourtSMSRepository:
    """短信仓储服务测试"""

    def setup_method(self) -> None:
        self.repository = CourtSMSRepository()

    def test_get_by_id_success(self) -> None:
        sms = _make_sms(content="测试短信内容", status="pending")
        result = self.repository.get_by_id(sms_id=sms.id)
        assert result.id == sms.id
        assert result.content == "测试短信内容"
        assert result.status == "pending"

    def test_get_by_id_not_found(self) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            self.repository.get_by_id(sms_id=999)
        assert "短信记录不存在" in str(exc_info.value.message)
        assert "ID=999" in str(exc_info.value.message)

    def test_save_success(self) -> None:
        sms = _make_sms(content="原内容", status="pending")
        sms.content = "新内容"
        sms.status = "processed"
        self.repository.save(sms=sms)
        sms.refresh_from_db()
        assert sms.content == "新内容"
        assert sms.status == "processed"

    def test_refresh_success(self) -> None:
        sms = _make_sms(content="原内容", status="pending")
        CourtSMS.objects.filter(id=sms.id).update(content="数据库中的新内容")
        refreshed_sms = self.repository.refresh(sms=sms)
        assert refreshed_sms.content == "数据库中的新内容"
        assert refreshed_sms.id == sms.id

    def test_set_error_success(self) -> None:
        sms = _make_sms(content="测试内容", status="pending", error_message=None)
        self.repository.set_error(sms=sms, message="处理失败：网络错误")
        sms.refresh_from_db()
        assert sms.error_message == "处理失败：网络错误"

    def test_set_error_updates_timestamp(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        original_updated_at = sms.updated_at
        self.repository.set_error(sms=sms, message="错误信息")
        sms.refresh_from_db()
        assert sms.updated_at > original_updated_at

    def test_clear_error_success(self) -> None:
        sms = _make_sms(content="测试内容", status="error", error_message="之前的错误")
        self.repository.clear_error(sms=sms)
        sms.refresh_from_db()
        assert sms.error_message is None

    def test_reset_retry_fields_success(self) -> None:
        sms = _make_sms(content="测试内容", status="error")
        self.repository.reset_retry_fields(sms=sms)
        assert sms.scraper_task is None
        assert sms.case is None
        assert sms.case_log is None
        assert sms.feishu_sent_at is None
        assert sms.feishu_error is None

    def test_set_status_success(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        self.repository.set_status(sms=sms, status="processed")
        sms.refresh_from_db()
        assert sms.status == "processed"
        assert sms.error_message is None

    def test_set_status_with_error_message(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        self.repository.set_status(sms=sms, status="error", error_message="处理失败")
        sms.refresh_from_db()
        assert sms.status == "error"
        assert sms.error_message == "处理失败"

    def test_set_status_clear_error_message(self) -> None:
        sms = _make_sms(content="测试内容", status="error", error_message="之前的错误")
        self.repository.set_status(sms=sms, status="processed", error_message=None)
        sms.refresh_from_db()
        assert sms.status == "processed"
        assert sms.error_message is None


@pytest.mark.django_db
class TestCourtSMSRepositoryEdgeCases:
    """短信仓储服务边界情况测试"""

    def setup_method(self) -> None:
        self.repository = CourtSMSRepository()

    def test_save_partial_update(self) -> None:
        sms = _make_sms(content="原内容", status="pending")
        sms.content = "新内容"
        sms.status = "processed"
        self.repository.save(sms=sms)
        sms.refresh_from_db()
        assert sms.content == "新内容"
        assert sms.status == "processed"

    def test_set_error_with_long_message(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        long_message = "错误" * 500
        self.repository.set_error(sms=sms, message=long_message)
        sms.refresh_from_db()
        assert sms.error_message == long_message

    def test_set_error_with_empty_message(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        self.repository.set_error(sms=sms, message="")
        sms.refresh_from_db()
        assert sms.error_message == ""

    def test_reset_retry_fields_already_none(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        self.repository.reset_retry_fields(sms=sms)
        assert sms.scraper_task is None
        assert sms.case is None
        assert sms.case_log is None

    def test_set_status_multiple_times(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        self.repository.set_status(sms=sms, status="processing")
        sms.refresh_from_db()
        assert sms.status == "processing"
        self.repository.set_status(sms=sms, status="processed")
        sms.refresh_from_db()
        assert sms.status == "processed"
        self.repository.set_status(sms=sms, status="error", error_message="失败")
        sms.refresh_from_db()
        assert sms.status == "error"
        assert sms.error_message == "失败"

    def test_refresh_after_external_modification(self) -> None:
        sms = _make_sms(content="原内容", status="pending")
        CourtSMS.objects.filter(id=sms.id).update(content="外部修改的内容", status="external_status")
        refreshed_sms = self.repository.refresh(sms=sms)
        assert refreshed_sms.content == "外部修改的内容"
        assert refreshed_sms.status == "external_status"

    def test_get_by_id_with_related_data(self) -> None:
        sms = _make_sms(content="测试内容", status="pending")
        result = self.repository.get_by_id(sms_id=sms.id)
        assert result.id == sms.id
        assert result.case is None
        assert result.case_log is None
