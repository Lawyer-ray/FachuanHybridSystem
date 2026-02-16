"""
文书识别手动案件绑定集成测试

测试完整流程：上传文书 → 识别 → 绑定失败 → 手动选择 → 绑定成功
验证日志创建和通知触发

Requirements: 3.1, 3.2, 4.4
"""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.utils import timezone

from apps.automation.models import DocumentRecognitionStatus, DocumentRecognitionTask
from apps.automation.services.court_document_recognition import CaseBindingService, CourtDocumentRecognitionService
from apps.automation.services.court_document_recognition.data_classes import BindingResult, DocumentType
from apps.cases.models import Case, CaseLog, CaseNumber
from apps.contracts.models import Contract
from apps.core.enums import CaseLogReminderType
from apps.organization.models import LawFirm, Lawyer


@pytest.mark.django_db
class TestManualCaseBindingIntegration:
    """手动案件绑定集成测试"""

    def setup_method(self):
        """测试前准备"""
        # 创建律所和律师（案件日志需要默认 actor）
        self.law_firm = LawFirm.objects.create(name="测试律所")
        self.lawyer = Lawyer.objects.create_user(
            username="testlawyer",
            password="testpass123",
            law_firm=self.law_firm,
        )

        # 创建测试合同
        self.contract = Contract.objects.create(
            name="测试合同",
            case_type="civil",
        )

        # 创建测试案件
        self.case = Case.objects.create(
            name="测试案件-张三诉李四",
            contract=self.contract,
        )

        # 创建案号
        self.case_number = CaseNumber.objects.create(
            case=self.case,
            number="(2024)京0101民初12345号",
        )

        # 创建临时文件
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self.temp_file.write(b"test pdf content")
        self.temp_file.close()

        # 创建识别任务（模拟自动绑定失败的情况）
        self.task = DocumentRecognitionTask.objects.create(
            file_path=self.temp_file.name,
            original_filename="test_summons.pdf",
            status=DocumentRecognitionStatus.SUCCESS,
            document_type="summons",
            case_number="(2024)京0101民初99999号",  # 不存在的案号
            key_time=timezone.now() + timedelta(days=7),
            confidence=0.95,
            extraction_method="pdf_text",
            raw_text="传票内容...",
            binding_success=False,
            binding_message="未找到案号 (2024)京0101民初99999号 对应的案件",
            binding_error_code="CASE_NOT_FOUND",
        )

    def teardown_method(self):
        """测试后清理"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    @patch(
        "apps.automation.services.court_document_recognition.case_binding_service.CaseBindingService._trigger_notification"
    )
    def test_manual_bind_success_creates_case_log(self, mock_notification):
        """
        测试手动绑定成功后创建案件日志

        Requirements: 3.1, 3.2
        """
        # 准备
        binding_service = CaseBindingService()

        # 执行手动绑定
        result = binding_service.manual_bind_document_to_case(task_id=self.task.id, case_id=self.case.id, user=None)

        # 验证绑定成功
        assert result.success is True
        assert result.case_id == self.case.id
        assert result.case_name == self.case.name
        assert result.case_log_id is not None

        # 验证案件日志创建
        case_log = CaseLog.objects.get(id=result.case_log_id)
        assert case_log.case_id == self.case.id
        assert "传票" in case_log.content

        # 验证任务状态更新
        self.task.refresh_from_db()
        assert self.task.binding_success is True
        assert self.task.case_id == self.case.id
        assert self.task.case_log_id == result.case_log_id

    @patch(
        "apps.automation.services.court_document_recognition.case_binding_service.CaseBindingService._trigger_notification"
    )
    def test_manual_bind_summons_sets_hearing_reminder(self, mock_notification):
        """
        测试手动绑定传票设置开庭提醒

        Requirements: 4.1, 4.2
        """
        # 准备
        binding_service = CaseBindingService()

        # 执行手动绑定
        result = binding_service.manual_bind_document_to_case(task_id=self.task.id, case_id=self.case.id, user=None)

        # 验证绑定成功
        assert result.success is True

        # 验证提醒类型为开庭
        case_log = CaseLog.objects.get(id=result.case_log_id)
        assert case_log.reminder_type == CaseLogReminderType.HEARING
        assert case_log.reminder_time is not None

    @patch(
        "apps.automation.services.court_document_recognition.notification_service.DocumentRecognitionNotificationService.send_notification"
    )
    def test_manual_bind_triggers_notification(self, mock_send_notification):
        """
        测试手动绑定成功后触发飞书通知

        Requirements: 4.4
        """
        from apps.automation.services.court_document_recognition.data_classes import NotificationResult

        # 配置 mock 返回成功
        mock_send_notification.return_value = NotificationResult.success_result(sent_at=timezone.now(), file_sent=True)

        # 准备
        binding_service = CaseBindingService()

        # 执行手动绑定
        result = binding_service.manual_bind_document_to_case(task_id=self.task.id, case_id=self.case.id, user=None)

        # 验证绑定成功
        assert result.success is True

        # 验证通知被调用
        mock_send_notification.assert_called_once()
        call_args = mock_send_notification.call_args
        assert call_args.kwargs["case_id"] == self.case.id
        assert call_args.kwargs["document_type"] == "summons"

        # 验证任务通知状态更新
        self.task.refresh_from_db()
        assert self.task.notification_sent is True

    def test_manual_bind_already_bound_task_fails(self):
        """
        测试已绑定任务再次绑定失败

        Requirements: 3.1
        """
        # 先绑定一次
        self.task.binding_success = True
        self.task.case = self.case
        self.task.save()

        # 准备
        binding_service = CaseBindingService()

        # 尝试再次绑定
        result = binding_service.manual_bind_document_to_case(task_id=self.task.id, case_id=self.case.id, user=None)

        # 验证绑定失败
        assert result.success is False
        assert result.error_code == "ALREADY_BOUND"

    def test_manual_bind_nonexistent_task_fails(self):
        """
        测试绑定不存在的任务失败

        Requirements: 3.1
        """
        # 准备
        binding_service = CaseBindingService()

        # 尝试绑定不存在的任务
        result = binding_service.manual_bind_document_to_case(task_id=99999, case_id=self.case.id, user=None)

        # 验证绑定失败
        assert result.success is False
        assert result.error_code == "TASK_NOT_FOUND"

    @patch(
        "apps.automation.services.court_document_recognition.case_binding_service.CaseBindingService._trigger_notification"
    )
    def test_manual_bind_nonexistent_case_fails(self, mock_notification):
        """
        测试绑定不存在的案件失败

        Requirements: 3.1
        """
        # 准备
        binding_service = CaseBindingService()

        # 尝试绑定不存在的案件
        result = binding_service.manual_bind_document_to_case(task_id=self.task.id, case_id=99999, user=None)

        # 验证绑定失败
        assert result.success is False
        assert result.error_code == "CASE_NOT_FOUND"


@pytest.mark.django_db
class TestManualCaseBindingAPIIntegration:
    """手动案件绑定 API 集成测试"""

    def setup_method(self):
        """测试前准备"""
        # 创建律所和律师
        self.law_firm = LawFirm.objects.create(name="API测试律所")
        self.lawyer = Lawyer.objects.create_user(
            username="apitestlawyer",
            password="testpass123",
            law_firm=self.law_firm,
        )

        # 创建测试合同
        self.contract = Contract.objects.create(
            name="API测试合同",
            case_type="civil",
        )

        # 创建测试案件
        self.case = Case.objects.create(
            name="API测试案件-王五诉赵六",
            contract=self.contract,
        )

        # 创建案号
        self.case_number = CaseNumber.objects.create(
            case=self.case,
            number="(2024)沪0101民初54321号",
        )

        # 创建临时文件
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self.temp_file.write(b"test pdf content")
        self.temp_file.close()

        # 创建识别任务
        self.task = DocumentRecognitionTask.objects.create(
            file_path=self.temp_file.name,
            original_filename="api_test_summons.pdf",
            status=DocumentRecognitionStatus.SUCCESS,
            document_type="summons",
            case_number="(2024)沪0101民初88888号",
            key_time=timezone.now() + timedelta(days=14),
            confidence=0.92,
            extraction_method="pdf_text",
            raw_text="API测试传票内容...",
            binding_success=False,
            binding_message="未找到案号对应的案件",
            binding_error_code="CASE_NOT_FOUND",
        )

    def teardown_method(self):
        """测试后清理"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_search_cases_api(self):
        """
        测试案件搜索 API

        Requirements: 1.3, 2.3
        """
        from django.test import Client

        client = Client()
        client.force_login(self.lawyer)

        # 搜索案件（使用正确的 API 路径）
        response = client.get("/api/v1/automation/court-document/search-cases", {"q": "王五"})

        assert response.status_code == 200
        data = response.json()

        # 验证返回结果
        assert isinstance(data, list)
        assert len(data) <= 20  # 限制返回数量

        # 验证搜索结果包含目标案件
        case_ids = [item["id"] for item in data]
        assert self.case.id in case_ids

    def test_search_cases_by_case_number(self):
        """
        测试按案号搜索案件

        Requirements: 1.3
        """
        from django.test import Client

        client = Client()
        client.force_login(self.lawyer)

        # 按案号搜索
        response = client.get("/api/v1/automation/court-document/search-cases", {"q": "54321"})

        assert response.status_code == 200
        data = response.json()

        # 验证搜索结果
        case_ids = [item["id"] for item in data]
        assert self.case.id in case_ids

    @patch(
        "apps.automation.services.court_document_recognition.case_binding_service.CaseBindingService._trigger_notification"
    )
    def test_manual_bind_api(self, mock_notification):
        """
        测试手动绑定 API

        Requirements: 3.1
        """
        import json

        from django.test import Client

        client = Client()
        client.force_login(self.lawyer)

        # 调用手动绑定 API（使用正确的 API 路径）
        response = client.post(
            f"/api/v1/automation/court-document/task/{self.task.id}/bind",
            data=json.dumps({"case_id": self.case.id}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()

        # 验证绑定成功
        assert data["success"] is True
        assert data["case_id"] == self.case.id
        assert data["case_name"] == self.case.name
        assert data["case_log_id"] is not None

        # 验证数据库状态
        self.task.refresh_from_db()
        assert self.task.binding_success is True
        assert self.task.case_id == self.case.id


@pytest.mark.django_db
class TestCompleteManualBindingFlow:
    """完整手动绑定流程测试"""

    def setup_method(self):
        """测试前准备"""
        from apps.cases.models import CaseParty
        from apps.client.models import Client as ClientModel

        # 创建律所和律师
        self.law_firm = LawFirm.objects.create(name="完整流程测试律所")
        self.lawyer = Lawyer.objects.create_user(
            username="flowlawyer",
            password="testpass123",
            law_firm=self.law_firm,
        )

        # 创建客户
        self.client_entity = ClientModel.objects.create(
            name="流程测试客户-张三",
            client_type=ClientModel.NATURAL,
            is_our_client=True,
        )

        # 创建测试合同
        self.contract = Contract.objects.create(
            name="完整流程测试合同",
            case_type="civil",
        )

        # 创建测试案件
        self.case = Case.objects.create(
            name="完整流程测试案件",
            contract=self.contract,
        )

        # 创建案号
        self.case_number = CaseNumber.objects.create(
            case=self.case,
            number="(2024)粤0101民初11111号",
        )

        # 创建当事人关联（使用正确的字段名 legal_status）
        CaseParty.objects.create(
            case=self.case,
            client=self.client_entity,
            legal_status="plaintiff",
        )

        # 创建临时文件
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self.temp_file.write(b"complete flow test pdf content")
        self.temp_file.close()

    def teardown_method(self):
        """测试后清理"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    @patch(
        "apps.automation.services.court_document_recognition.notification_service.DocumentRecognitionNotificationService.send_notification"
    )
    def test_complete_flow_upload_recognize_fail_manual_bind_success(self, mock_send_notification):
        """
        测试完整流程：上传 → 识别 → 自动绑定失败 → 手动绑定成功

        Requirements: 3.1, 3.2, 4.4
        """
        from apps.automation.services.court_document_recognition.data_classes import NotificationResult

        # 配置通知 mock
        mock_send_notification.return_value = NotificationResult.success_result(sent_at=timezone.now(), file_sent=True)

        # 步骤1：创建识别任务（模拟上传和识别）
        task = DocumentRecognitionTask.objects.create(
            file_path=self.temp_file.name,
            original_filename="complete_flow_summons.pdf",
            status=DocumentRecognitionStatus.SUCCESS,
            document_type="summons",
            case_number="(2024)粤0101民初99999号",  # 不存在的案号
            key_time=timezone.now() + timedelta(days=10),
            confidence=0.88,
            extraction_method="pdf_text",
            raw_text="完整流程测试传票内容...",
            binding_success=False,
            binding_message="未找到案号对应的案件",
            binding_error_code="CASE_NOT_FOUND",
        )

        # 验证初始状态：自动绑定失败
        assert task.binding_success is False
        assert task.case_id is None

        # 步骤2：执行手动绑定
        binding_service = CaseBindingService()
        result = binding_service.manual_bind_document_to_case(task_id=task.id, case_id=self.case.id, user=self.lawyer)

        # 验证绑定成功
        assert result.success is True
        assert result.case_id == self.case.id
        assert result.case_log_id is not None

        # 步骤3：验证案件日志创建
        case_log = CaseLog.objects.get(id=result.case_log_id)
        assert case_log.case_id == self.case.id
        assert "传票" in case_log.content
        assert case_log.reminder_type == CaseLogReminderType.HEARING

        # 步骤4：验证通知触发
        mock_send_notification.assert_called_once()

        # 步骤5：验证任务状态更新
        task.refresh_from_db()
        assert task.binding_success is True
        assert task.case_id == self.case.id
        assert task.case_log_id == result.case_log_id
        assert task.notification_sent is True
        assert "手动绑定" in task.binding_message
