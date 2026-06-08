"""Automation Model 测试 - CourtSMS, ScraperTask, CourtToken"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.automation.models import (
    CourtSMS,
    CourtSMSStatus,
    CourtSMSType,
    ScraperTask,
    ScraperTaskStatus,
    ScraperTaskType,
    CourtToken,
)


@pytest.mark.django_db
class TestCourtSMSModel:
    """CourtSMS 模型测试"""

    def test_create_sms(self) -> None:
        """创建短信记录"""
        sms = CourtSMS.objects.create(
            content="测试短信内容",
            received_at=timezone.now(),
            sms_type=CourtSMSType.DOCUMENT_DELIVERY,
            status=CourtSMSStatus.PENDING,
        )
        assert sms.content == "测试短信内容"
        assert sms.sms_type == CourtSMSType.DOCUMENT_DELIVERY
        assert sms.status == CourtSMSStatus.PENDING

    def test_sms_status_choices(self) -> None:
        """短信状态选项应完整"""
        assert CourtSMSStatus.PENDING == "pending"
        assert CourtSMSStatus.PARSING == "parsing"
        assert CourtSMSStatus.DOWNLOADING == "downloading"
        assert CourtSMSStatus.COMPLETED == "completed"
        assert CourtSMSStatus.FAILED == "failed"

    def test_sms_type_choices(self) -> None:
        """短信类型选项应完整"""
        assert CourtSMSType.DOCUMENT_DELIVERY == "document_delivery"
        assert CourtSMSType.INFO_NOTIFICATION == "info_notification"
        assert CourtSMSType.FILING_NOTIFICATION == "filing_notification"

    def test_sms_with_download_links(self) -> None:
        """创建短信包含下载链接"""
        links = ["https://example.com/doc1.pdf", "https://example.com/doc2.pdf"]
        sms = CourtSMS.objects.create(
            content="下载链接短信",
            received_at=timezone.now(),
            download_links=links,
        )
        assert sms.download_links == links

    def test_sms_with_case_numbers(self) -> None:
        """创建短信包含案号"""
        case_numbers = ["（2024）京0101民初123号"]
        sms = CourtSMS.objects.create(
            content="案号短信",
            received_at=timezone.now(),
            case_numbers=case_numbers,
        )
        assert sms.case_numbers == case_numbers


@pytest.mark.django_db
class TestScraperTaskModel:
    """ScraperTask 模型测试"""

    def test_create_task(self) -> None:
        """创建爬虫任务"""
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.PENDING,
            url="https://example.com",
        )
        assert task.task_type == ScraperTaskType.COURT_DOCUMENT
        assert task.status == ScraperTaskStatus.PENDING

    def test_task_status_choices(self) -> None:
        """任务状态选项应完整"""
        assert ScraperTaskStatus.PENDING == "pending"
        assert ScraperTaskStatus.RUNNING == "running"
        assert ScraperTaskStatus.SUCCESS == "success"
        assert ScraperTaskStatus.FAILED == "failed"

    def test_task_type_choices(self) -> None:
        """任务类型选项应完整"""
        assert ScraperTaskType.COURT_DOCUMENT == "court_document"
        assert ScraperTaskType.COURT_FILING == "court_filing"

    def test_task_with_config(self) -> None:
        """创建任务包含配置"""
        config = {"username": "test", "password": "test"}
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.PENDING,
            url="https://example.com",
            config=config,
        )
        assert task.config == config

    def test_task_with_result(self) -> None:
        """创建任务包含结果"""
        result = {"files": ["/path/to/file.pdf"], "success": True}
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.SUCCESS,
            url="https://example.com",
            result=result,
        )
        assert task.result == result

    def test_task_with_retry(self) -> None:
        """创建任务包含重试信息"""
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.PENDING,
            url="https://example.com",
            retry_count=2,
            max_retries=3,
        )
        assert task.retry_count == 2
        assert task.max_retries == 3

    def test_task_with_case(self) -> None:
        """创建任务关联案件"""
        from apps.cases.models import Case
        from apps.contracts.models import Contract

        contract = Contract.objects.create(name="爬虫测试合同", case_type="civil")
        case = Case.objects.create(name="爬虫测试案件", contract=contract)
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.PENDING,
            url="https://example.com",
            case=case,
        )
        assert task.case.name == "爬虫测试案件"


@pytest.mark.django_db
class TestCourtTokenModel:
    """CourtToken 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回站点和账号"""
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="test_account",
            token="test_token",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert "court_zxfw" in str(token)
        assert "test_account" in str(token)

    def test_is_expired_valid(self) -> None:
        """is_expired 应返回 False 对有效 token"""
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="valid_account",
            token="valid_token",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert token.is_expired() is False

    def test_is_expired_expired(self) -> None:
        """is_expired 应返回 True 对过期 token"""
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="expired_account",
            token="expired_token",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert token.is_expired() is True

    def test_unique_together(self) -> None:
        """site_name 和 account 应唯一"""
        CourtToken.objects.create(
            site_name="court_zxfw",
            account="unique_account",
            token="token1",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        with pytest.raises(Exception):  # noqa: B017
            CourtToken.objects.create(
                site_name="court_zxfw",
                account="unique_account",
                token="token2",
                expires_at=timezone.now() + timedelta(hours=2),
            )

    def test_token_type_default(self) -> None:
        """token_type 默认应为 Bearer"""
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="default_type_account",
            token="default_type_token",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert token.token_type == "Bearer"
