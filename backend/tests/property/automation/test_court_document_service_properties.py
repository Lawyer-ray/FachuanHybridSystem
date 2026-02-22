"""
CourtDocumentService 属性测试
使用 Hypothesis 进行基于属性的测试
"""

from datetime import datetime

import pytest
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.models import CourtDocument, DocumentDownloadStatus, ScraperTask
from apps.automation.services.scraper.court_document_service import CourtDocumentService


# 定义策略
@st.composite
def api_data_strategy(draw):
    """生成有效的 API 数据"""
    # 使用安全的字符集，排除 surrogate 字符和其他问题字符
    safe_text = st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(
            blacklist_categories=("Cs",), blacklist_characters="\x00"  # type: ignore
        ),
    )

    return {
        "c_sdbh": draw(safe_text),
        "c_stbh": draw(safe_text),
        "wjlj": f"https://example.com/{draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))}",
        "c_wsbh": draw(safe_text),
        "c_wsmc": draw(safe_text),
        "c_fybh": draw(safe_text),
        "c_fymc": draw(safe_text),
        "c_wjgs": draw(st.sampled_from(["pdf", "doc", "docx", "txt"])),
        "dt_cjsj": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2025, 12, 31))).isoformat(),
    }


@pytest.mark.django_db
class TestCourtDocumentServiceProperties:
    """CourtDocumentService 属性测试"""

    def setup_method(self):
        """测试前准备"""
        self.service = CourtDocumentService()

        # 创建测试用的爬虫任务
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document", status="running", url="https://test.example.com", priority=5
        )

    @settings(max_examples=100, deadline=None)
    @given(api_data=api_data_strategy())
    def test_property_9_database_record_creation(self, api_data):
        """
        属性 9: 数据库记录创建

        Feature: court-document-api-optimization, Property 9: 数据库记录创建

        对于任何成功拦截的API响应，系统应该为每条文书数据创建对应的数据库记录
        验证需求: 3.1
        """
        # 执行创建
        document = self.service.create_document_from_api_data(scraper_task_id=self.scraper_task.id, api_data=api_data)

        # 验证：记录已创建
        assert document.id is not None

        # 验证：记录可以从数据库查询到
        retrieved_document = CourtDocument.objects.get(id=document.id)
        assert retrieved_document is not None

        # 验证：所有字段都正确保存
        assert retrieved_document.c_sdbh == api_data["c_sdbh"]
        assert retrieved_document.c_stbh == api_data["c_stbh"]
        assert retrieved_document.wjlj == api_data["wjlj"]
        assert retrieved_document.c_wsbh == api_data["c_wsbh"]
        assert retrieved_document.c_wsmc == api_data["c_wsmc"]
        assert retrieved_document.c_fybh == api_data["c_fybh"]
        assert retrieved_document.c_fymc == api_data["c_fymc"]
        assert retrieved_document.c_wjgs == api_data["c_wjgs"]

        # 验证：初始状态为 PENDING
        assert retrieved_document.download_status == DocumentDownloadStatus.PENDING

        # 清理
        document.delete()

    @settings(max_examples=100, deadline=None)
    @given(
        api_data=api_data_strategy(),
        file_path=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")) | st.sampled_from("/-_."),
        ),
        file_size=st.integers(min_value=1, max_value=10000000),
    )
    def test_property_11_download_status_sync(self, api_data, file_path, file_size):
        """
        属性 11: 下载状态同步

        Feature: court-document-api-optimization, Property 11: 下载状态同步

        对于任何下载成功的文书，数据库记录的 download_status 应该更新为 "success"，
        并且 local_file_path 应该被设置
        验证需求: 3.3
        """
        # 先创建文书记录
        document = self.service.create_document_from_api_data(scraper_task_id=self.scraper_task.id, api_data=api_data)

        # 更新为成功状态
        updated_document = self.service.update_download_status(
            document_id=document.id,
            status=DocumentDownloadStatus.SUCCESS,
            local_file_path=file_path,
            file_size=file_size,
        )

        # 验证：状态已更新为 SUCCESS
        assert updated_document.download_status == DocumentDownloadStatus.SUCCESS

        # 验证：文件路径已设置
        assert updated_document.local_file_path == file_path

        # 验证：文件大小已设置
        assert updated_document.file_size == file_size

        # 验证：下载完成时间已设置
        assert updated_document.downloaded_at is not None

        # 验证：从数据库重新查询，状态仍然正确
        retrieved_document = CourtDocument.objects.get(id=document.id)
        assert retrieved_document.download_status == DocumentDownloadStatus.SUCCESS
        assert retrieved_document.local_file_path == file_path
        assert retrieved_document.file_size == file_size
        assert retrieved_document.downloaded_at is not None

        # 清理
        document.delete()

    @settings(max_examples=100, deadline=None)
    @given(
        api_data=api_data_strategy(),
        error_message=st.text(
            min_size=1,
            max_size=500,
            alphabet=st.characters(
                blacklist_categories=("Cs",), blacklist_characters="\x00"  # type: ignore
            ),
        ),
    )
    def test_property_12_failed_status_recording(self, api_data, error_message):
        """
        属性 12: 失败状态记录

        Feature: court-document-api-optimization, Property 12: 失败状态记录

        对于任何下载失败的文书，数据库记录的 download_status 应该更新为 "failed"，
        并且 error_message 应该包含错误信息
        验证需求: 3.4
        """
        # 先创建文书记录
        document = self.service.create_document_from_api_data(scraper_task_id=self.scraper_task.id, api_data=api_data)

        # 更新为失败状态
        updated_document = self.service.update_download_status(
            document_id=document.id, status=DocumentDownloadStatus.FAILED, error_message=error_message
        )

        # 验证：状态已更新为 FAILED
        assert updated_document.download_status == DocumentDownloadStatus.FAILED

        # 验证：错误信息已设置
        assert updated_document.error_message == error_message

        # 验证：下载完成时间未设置（因为失败了）
        assert updated_document.downloaded_at is None

        # 验证：从数据库重新查询，状态仍然正确
        retrieved_document = CourtDocument.objects.get(id=document.id)
        assert retrieved_document.download_status == DocumentDownloadStatus.FAILED
        assert retrieved_document.error_message == error_message
        assert retrieved_document.downloaded_at is None

        # 清理
        document.delete()
