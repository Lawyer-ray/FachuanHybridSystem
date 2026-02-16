"""
Automation app 集成测试

通过直接调用 API 函数测试核心自动化任务 API 流程。
覆盖法院短信提交、文书送达定时任务 CRUD。

Requirements: 5.5
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.automation.api.court_sms_api import submit_sms
from apps.automation.api.document_delivery_api import (
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
    DocumentDeliveryScheduleCreateIn,
    DocumentDeliveryScheduleUpdateIn,
)
from apps.automation.models import (
    CourtSMS,
    CourtSMSStatus,
    DocumentDeliverySchedule,
)
from apps.automation.schemas.court_sms import CourtSMSSubmitIn
from apps.core.exceptions import NotFoundError
from apps.organization.models import AccountCredential
from tests.factories.organization_factories import LawyerFactory


def _make_request(user: Any = None) -> Mock:
    """构造模拟 request 对象。"""
    request = Mock()
    request.user = user
    return request


# ============================================================================
# 法院短信提交 API 测试
# ============================================================================


@pytest.mark.django_db
@pytest.mark.integration
class TestCourtSMSSubmitAPI:
    """法院短信提交 API 测试"""

    def _create_mock_sms(self, content: str = "测试短信") -> Mock:
        """创建模拟 SMS 对象。"""
        sms = Mock()
        sms.id = 1
        sms.status = CourtSMSStatus.PENDING
        sms.created_at = timezone.now()
        sms.content = content
        return sms

    def test_submit_sms_success(self) -> None:
        """提交法院短信成功"""
        mock_sms = self._create_mock_sms("【佛山市禅城区人民法院】尊敬的律师，您有一份文书待查收")
        request = _make_request()
        payload = CourtSMSSubmitIn(
            content="【佛山市禅城区人民法院】尊敬的律师，您有一份文书待查收",
            received_at=timezone.now(),
        )

        with patch(
            "apps.automation.api.court_sms_api._get_court_sms_service"
        ) as mock_factory:
            mock_service = Mock()
            mock_service.submit_sms.return_value = mock_sms
            mock_factory.return_value = mock_service

            result = submit_sms(request, payload)

        assert result.success is True
        assert result.data["id"] == 1
        assert result.data["status"] == CourtSMSStatus.PENDING
        mock_service.submit_sms.assert_called_once()

    def test_submit_sms_minimal(self) -> None:
        """最小字段提交短信"""
        mock_sms = self._create_mock_sms()
        request = _make_request()
        payload = CourtSMSSubmitIn(content="测试短信内容")

        with patch(
            "apps.automation.api.court_sms_api._get_court_sms_service"
        ) as mock_factory:
            mock_service = Mock()
            mock_service.submit_sms.return_value = mock_sms
            mock_factory.return_value = mock_service

            result = submit_sms(request, payload)

        assert result.success is True
        assert result.data["id"] is not None

    def test_submit_sms_empty_content_rejected(self) -> None:
        """空内容被 Schema 验证拒绝"""
        with pytest.raises(Exception):
            CourtSMSSubmitIn(content="")


# ============================================================================
# 文书送达定时任务 CRUD API 测试
# ============================================================================


def _create_credential() -> AccountCredential:
    """创建测试凭证。"""
    lawyer = LawyerFactory()
    return AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="court_zxfw",
        account="test_account",
        password="test_password",
    )



@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentDeliveryScheduleCreateAPI:
    """文书送达定时任务创建 API 测试"""

    def test_create_schedule_success(self) -> None:
        """创建定时任务成功"""
        credential = _create_credential()
        request = _make_request()

        payload = DocumentDeliveryScheduleCreateIn(
            credential_id=credential.id,
            runs_per_day=2,
            hour_interval=12,
            cutoff_hours=24,
            is_active=True,
        )

        result = create_schedule(request, payload)

        assert result.id is not None
        assert result.credential_id == credential.id
        assert result.runs_per_day == 2
        assert result.hour_interval == 12
        assert result.cutoff_hours == 24
        assert result.is_active is True
        assert result.next_run_at is not None

    def test_create_schedule_defaults(self) -> None:
        """使用默认值创建定时任务"""
        credential = _create_credential()
        request = _make_request()

        payload = DocumentDeliveryScheduleCreateIn(credential_id=credential.id)

        result = create_schedule(request, payload)

        assert result.runs_per_day == 1
        assert result.hour_interval == 24
        assert result.cutoff_hours == 24
        assert result.is_active is True

    def test_create_schedule_duplicate_credential(self) -> None:
        """同一凭证不能创建重复定时任务"""
        credential = _create_credential()
        request = _make_request()

        payload = DocumentDeliveryScheduleCreateIn(credential_id=credential.id)
        create_schedule(request, payload)

        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            create_schedule(request, payload)


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentDeliveryScheduleListAPI:
    """文书送达定时任务列表 API 测试"""

    def test_list_schedules_empty(self) -> None:
        """空列表查询"""
        request = _make_request()

        result = list_schedules(request)
        # @paginate 装饰器返回 {'items': [...], 'count': N}
        assert result["count"] == 0
        assert len(result["items"]) == 0

    def test_list_schedules_returns_all(self) -> None:
        """查询所有定时任务"""
        cred1 = _create_credential()
        cred2 = _create_credential()
        DocumentDeliverySchedule.objects.create(
            credential=cred1, runs_per_day=1, hour_interval=24, cutoff_hours=24,
        )
        DocumentDeliverySchedule.objects.create(
            credential=cred2, runs_per_day=2, hour_interval=12, cutoff_hours=48,
        )

        request = _make_request()
        result = list_schedules(request)
        assert result["count"] == 2
        assert len(result["items"]) == 2

    def test_list_schedules_filter_by_active(self) -> None:
        """按启用状态筛选"""
        cred1 = _create_credential()
        cred2 = _create_credential()
        DocumentDeliverySchedule.objects.create(
            credential=cred1, is_active=True,
        )
        DocumentDeliverySchedule.objects.create(
            credential=cred2, is_active=False,
        )

        request = _make_request()
        result = list_schedules(request, is_active=True)
        assert result["count"] == 1
        assert len(result["items"]) == 1


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentDeliveryScheduleGetAPI:
    """文书送达定时任务详情 API 测试"""

    def test_get_schedule_success(self) -> None:
        """获取定时任务详情"""
        credential = _create_credential()
        schedule = DocumentDeliverySchedule.objects.create(
            credential=credential, runs_per_day=3, hour_interval=8, cutoff_hours=48,
        )

        request = _make_request()
        result = get_schedule(request, schedule.id)

        assert result.id == schedule.id
        assert result.runs_per_day == 3
        assert result.hour_interval == 8
        assert result.cutoff_hours == 48

    def test_get_schedule_not_found(self) -> None:
        """获取不存在的定时任务"""
        request = _make_request()

        with pytest.raises(NotFoundError):
            get_schedule(request, 999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentDeliveryScheduleUpdateAPI:
    """文书送达定时任务更新 API 测试"""

    def test_update_schedule_partial(self) -> None:
        """部分更新定时任务"""
        credential = _create_credential()
        schedule = DocumentDeliverySchedule.objects.create(
            credential=credential, runs_per_day=1, hour_interval=24,
            cutoff_hours=24, is_active=True,
        )

        request = _make_request()
        payload = DocumentDeliveryScheduleUpdateIn(cutoff_hours=48)
        result = update_schedule(request, schedule.id, payload)

        assert result.cutoff_hours == 48
        assert result.runs_per_day == 1  # 未更新的字段保持不变
        assert result.hour_interval == 24

    def test_update_schedule_deactivate(self) -> None:
        """禁用定时任务"""
        credential = _create_credential()
        schedule = DocumentDeliverySchedule.objects.create(
            credential=credential, is_active=True,
            next_run_at=timezone.now(),
        )

        request = _make_request()
        payload = DocumentDeliveryScheduleUpdateIn(is_active=False)
        result = update_schedule(request, schedule.id, payload)

        assert result.is_active is False

    def test_update_schedule_not_found(self) -> None:
        """更新不存在的定时任务"""
        request = _make_request()
        payload = DocumentDeliveryScheduleUpdateIn(runs_per_day=2)

        with pytest.raises(NotFoundError):
            update_schedule(request, 999999, payload)


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentDeliveryScheduleDeleteAPI:
    """文书送达定时任务删除 API 测试"""

    def test_delete_schedule_success(self) -> None:
        """删除定时任务"""
        credential = _create_credential()
        schedule = DocumentDeliverySchedule.objects.create(credential=credential)
        schedule_id = schedule.id

        request = _make_request()
        result = delete_schedule(request, schedule_id)

        assert result["success"] is True
        assert not DocumentDeliverySchedule.objects.filter(id=schedule_id).exists()

    def test_delete_schedule_not_found(self) -> None:
        """删除不存在的定时任务"""
        request = _make_request()

        with pytest.raises(NotFoundError):
            delete_schedule(request, 999999)
