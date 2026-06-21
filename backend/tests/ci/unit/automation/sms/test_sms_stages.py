"""SMS 处理阶段测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.stages.sms_parsing_stage import SMSParsingStage
from apps.automation.services.sms.stages.sms_downloading_stage import SMSDownloadingStage
from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage
from apps.automation.services.sms.stages.sms_renaming_stage import SMSRenamingStage
from apps.automation.services.sms.stages.sms_notifying_stage import SMSNotifyingStage
from apps.automation.services.sms.sms_parser_service import SMSParseResult


def _make_sms(id=1, status="pending", content="", download_links=None, case_numbers=None,
              party_names=None, case=None, scraper_task=None, case_log=None, case_id=None,
              sms_type=None, retry_count=0, error_message=""):
    return SimpleNamespace(
        id=id,
        status=status,
        content=content,
        download_links=download_links or [],
        case_numbers=case_numbers or [],
        party_names=party_names or [],
        case=case,
        case_id=case_id,
        scraper_task=scraper_task,
        case_log=case_log,
        sms_type=sms_type,
        retry_count=retry_count,
        error_message=error_message,
        save=MagicMock(),
        received_at=None,
        notification_results=None,
        feishu_sent_at=None,
        delivery_event_id=None,
        delivery_event_key=None,
        document_file_paths=None,
        get_sms_type_display=lambda: sms_type or "未分类",
    )


class TestSMSParsingStage:
    """SMSParsingStage 测试。"""

    def setup_method(self) -> None:
        self.parser = MagicMock()
        self.stage = SMSParsingStage(parser=self.parser)

    def test_stage_name(self) -> None:
        assert self.stage.stage_name == "解析"

    def test_can_process_pending(self) -> None:
        sms = _make_sms(status="pending")
        assert self.stage.can_process(sms) is True

    def test_can_process_non_pending(self) -> None:
        sms = _make_sms(status="parsing")
        assert self.stage.can_process(sms) is False

    def test_process_success(self) -> None:
        """成功解析短信。"""
        sms = _make_sms(status="pending", content="测试短信内容")
        self.parser.parse.return_value = SMSParseResult(
            sms_type="filing_notification",
            download_links=["https://example.com/doc"],
            case_numbers=["（2025）粤0604民初12345号"],
            party_names=["张三", "李四"],
            has_valid_download_link=True,
        )

        result = self.stage.process(sms)
        assert result.sms_type == "filing_notification"
        assert len(result.download_links) == 1
        assert len(result.case_numbers) == 1
        sms.save.assert_called()


class TestSMSDownloadingStage:
    """SMSDownloadingStage 测试。"""

    def setup_method(self) -> None:
        self.task_queue = MagicMock()
        self.execute_scraper_task = MagicMock()
        self.stage = SMSDownloadingStage(
            task_queue=self.task_queue,
            execute_scraper_task=self.execute_scraper_task,
        )

    def test_stage_name(self) -> None:
        assert self.stage.stage_name == "下载"

    def test_can_process_parsing(self) -> None:
        sms = _make_sms(status="parsing")
        assert self.stage.can_process(sms) is True

    def test_can_process_non_parsing(self) -> None:
        sms = _make_sms(status="pending")
        assert self.stage.can_process(sms) is False

    def test_process_no_download_links(self) -> None:
        """无下载链接，直接进入匹配阶段。"""
        sms = _make_sms(status="parsing", download_links=[])
        result = self.stage.process(sms)
        assert result.status == "matching"

    @patch("apps.automation.services.sms.stages.sms_downloading_stage.ScraperTask")
    def test_process_with_download_links(self, mock_scraper_task_cls) -> None:
        """有下载链接，创建下载任务。"""
        mock_task = MagicMock()
        mock_task.id = 100
        mock_scraper_task_cls.objects.create.return_value = mock_task
        self.task_queue.enqueue.return_value = "queue_task_100"

        sms = _make_sms(status="parsing", download_links=["https://example.com/doc"])
        result = self.stage.process(sms)
        assert result.status == "downloading"
        assert result.scraper_task == mock_task


class TestSMSMatchingStage:
    """SMSMatchingStage 测试。"""

    def setup_method(self) -> None:
        self.matcher = MagicMock()
        self.case_number_extractor = MagicMock()
        self.case_service = MagicMock()
        self.lawyer_service = MagicMock()
        self.stage = SMSMatchingStage(
            matcher=self.matcher,
            case_number_extractor=self.case_number_extractor,
            case_service=self.case_service,
            lawyer_service=self.lawyer_service,
        )

    def test_stage_name(self) -> None:
        assert self.stage.stage_name == "匹配"

    def test_can_process_matching(self) -> None:
        sms = _make_sms(status="matching")
        assert self.stage.can_process(sms) is True

    def test_can_process_non_matching(self) -> None:
        sms = _make_sms(status="pending")
        assert self.stage.can_process(sms) is False

    def test_process_match_success(self) -> None:
        """匹配成功。"""
        from apps.core.models.enums import CaseStatus

        case = SimpleNamespace(id=1, name="测试案件", status=CaseStatus.ACTIVE)
        self.matcher.match.return_value = case
        self.matcher.extract_parties_from_document.return_value = []
        admin = SimpleNamespace(id=1)
        self.lawyer_service.get_admin_lawyer.return_value = admin
        self.lawyer_service.get_lawyer_model.return_value = admin

        # Mock _create_case_binding to return True
        self.stage._create_case_binding = MagicMock(return_value=True)

        sms = _make_sms(status="matching", party_names=["张三", "李四"])
        result = self.stage.process(sms)
        assert result.status == "renaming"
        assert result.case_id == 1

    def test_process_no_match(self) -> None:
        """匹配失败。"""
        self.matcher.match.return_value = None
        self.matcher.extract_parties_from_document.return_value = []

        sms = _make_sms(status="matching", party_names=["张三", "李四"])
        result = self.stage.process(sms)
        assert result.status == "pending_manual"

    def test_process_manual_case(self) -> None:
        """已手动指定案件。"""
        case = SimpleNamespace(id=1, name="测试案件")
        admin = SimpleNamespace(id=1)
        self.lawyer_service.get_admin_lawyer.return_value = admin
        self.lawyer_service.get_lawyer_model.return_value = admin

        # Mock _create_case_binding to return True
        self.stage._create_case_binding = MagicMock(return_value=True)

        sms = _make_sms(status="matching", case=case)
        result = self.stage.process(sms)
        assert result.status == "renaming"

    def test_filter_valid_case_numbers(self) -> None:
        """过滤无效案号。"""
        valid = self.stage._filter_valid_case_numbers([
            "（2025）粤0604民初12345号",
            "2025年1月1号",
        ])
        assert "（2025）粤0604民初12345号" in valid


class TestSMSRenamingStage:
    """SMSRenamingStage 测试。"""

    def setup_method(self) -> None:
        self.document_attachment = MagicMock()
        self.case_number_extractor = MagicMock()
        self.matcher = MagicMock()
        self.lawyer_service = MagicMock()
        self.stage = SMSRenamingStage(
            document_attachment=self.document_attachment,
            case_number_extractor=self.case_number_extractor,
            matcher=self.matcher,
            lawyer_service=self.lawyer_service,
        )

    def test_stage_name(self) -> None:
        assert self.stage.stage_name == "重命名"

    def test_can_process_renaming(self) -> None:
        sms = _make_sms(status="renaming")
        assert self.stage.can_process(sms) is True

    def test_process_no_scraper_task(self) -> None:
        """无下载任务，跳过重命名。"""
        sms = _make_sms(status="renaming", scraper_task=None)
        result = self.stage.process(sms)
        assert result.status == "notifying"

    def test_process_no_documents_to_rename(self) -> None:
        """无可重命名文书。"""
        self.document_attachment.get_paths_for_renaming.return_value = []
        sms = _make_sms(status="renaming", scraper_task=MagicMock())
        result = self.stage.process(sms)
        assert result.status == "notifying"

    def test_process_rename_success(self) -> None:
        """重命名成功。"""
        self.document_attachment.get_paths_for_renaming.return_value = ["/path/doc1.pdf"]
        self.document_attachment.rename_documents.return_value = ["/path/renamed_doc1.pdf"]
        self.matcher.extract_parties_from_document.return_value = []

        scraper_task = MagicMock()
        scraper_task.result = {}
        sms = _make_sms(status="renaming", scraper_task=scraper_task, case=SimpleNamespace(id=1))
        result = self.stage.process(sms)
        assert result.status == "notifying"

    def test_process_rename_exception(self) -> None:
        """重命名异常不影响流程。"""
        self.document_attachment.get_paths_for_renaming.side_effect = Exception("error")
        sms = _make_sms(status="renaming", scraper_task=MagicMock())
        result = self.stage.process(sms)
        # 异常后仍进入 notifying 阶段
        assert result.status == "notifying"


class TestSMSNotifyingStage:
    """SMSNotifyingStage 测试。"""

    def setup_method(self) -> None:
        self.notification_service = MagicMock()
        self.document_attachment_service = MagicMock()
        self.stage = SMSNotifyingStage(
            notification_service=self.notification_service,
            document_attachment_service=self.document_attachment_service,
        )

    def test_stage_name(self) -> None:
        assert self.stage.stage_name == "通知"

    def test_can_process_notifying(self) -> None:
        sms = _make_sms(status="notifying")
        assert self.stage.can_process(sms) is True

    def test_process_no_case(self) -> None:
        """未绑定案件。"""
        from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult

        self.document_attachment_service.get_paths_for_notification.return_value = []
        sms = _make_sms(status="notifying", case=None)
        result = self.stage.process(sms)
        assert result.status == "completed"

    def test_process_notification_success(self) -> None:
        """通知发送成功。"""
        from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult

        self.document_attachment_service.get_paths_for_notification.return_value = ["/path/doc.pdf"]
        self.notification_service.send_case_chat_notification.return_value = MultiPlatformNotificationResult(
            attempts=[PlatformNotificationResult(platform="feishu", success=True)]
        )

        case = SimpleNamespace(id=1)
        sms = _make_sms(status="notifying", case=case)
        result = self.stage.process(sms)
        assert result.status == "completed"

    def test_process_notification_failure(self) -> None:
        """通知发送失败，不影响归档。"""
        from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult

        self.document_attachment_service.get_paths_for_notification.return_value = []
        self.notification_service.send_case_chat_notification.return_value = MultiPlatformNotificationResult(
            attempts=[PlatformNotificationResult(platform="feishu", success=False, error="网络错误")]
        )

        case = SimpleNamespace(id=1)
        sms = _make_sms(status="notifying", case=case)
        result = self.stage.process(sms)
        # 失败也标记为完成（不影响文书归档）
        assert result.status == "completed"
