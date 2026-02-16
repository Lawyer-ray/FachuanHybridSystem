"""
法院文书数据持久化集成测试
测试从 API 数据到数据库保存的完整流程
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.automation.models import CourtDocument, DocumentDownloadStatus, ScraperTask
from apps.automation.services.scraper.scrapers.court_document import CourtDocumentScraper
from apps.core.path import Path


@pytest.mark.django_db
class TestCourtDocumentPersistence:
    """法院文书数据持久化集成测试"""

    def setup_method(self):
        """测试前准备"""
        # 创建测试用的爬虫任务
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document", status="running", url="https://zxfw.court.gov.cn/test", priority=5
        )

    def test_save_document_to_db_success(self):
        """测试成功保存文书记录到数据库"""
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)

        # 准备测试数据
        document_data = {
            "c_sdbh": "test_sdbh_001",
            "c_stbh": "test_stbh_001",
            "wjlj": "https://example.com/doc1.pdf",
            "c_wsbh": "test_wsbh_001",
            "c_wsmc": "测试文书001",
            "c_fybh": "test_fybh_001",
            "c_fymc": "测试法院",
            "c_wjgs": "pdf",
            "dt_cjsj": "2024-01-01T00:00:00",
        }

        download_result = (True, "/tmp/test_doc1.pdf", None)

        # 调用保存方法
        document_id = scraper._save_document_to_db(document_data, download_result)

        # 验证：应该返回文书 ID
        assert document_id is not None, "应该返回文书 ID"

        # 验证：数据库中应该有记录
        document = CourtDocument.objects.get(id=document_id)
        assert document.c_sdbh == "test_sdbh_001"
        assert document.c_wsmc == "测试文书001"
        assert document.download_status == DocumentDownloadStatus.SUCCESS
        assert document.local_file_path == "/tmp/test_doc1.pdf"
        assert document.downloaded_at is not None

    def test_save_document_to_db_download_failed(self):
        """测试保存下载失败的文书记录"""
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)

        # 准备测试数据
        document_data = {
            "c_sdbh": "test_sdbh_002",
            "c_stbh": "test_stbh_002",
            "wjlj": "https://example.com/doc2.pdf",
            "c_wsbh": "test_wsbh_002",
            "c_wsmc": "测试文书002",
            "c_fybh": "test_fybh_002",
            "c_fymc": "测试法院",
            "c_wjgs": "pdf",
            "dt_cjsj": "2024-01-01T00:00:00",
        }

        download_result = (False, None, "下载超时")

        # 调用保存方法
        document_id = scraper._save_document_to_db(document_data, download_result)

        # 验证：应该返回文书 ID
        assert document_id is not None, "即使下载失败也应该保存记录"

        # 验证：数据库中应该有记录
        document = CourtDocument.objects.get(id=document_id)
        assert document.download_status == DocumentDownloadStatus.FAILED
        assert document.local_file_path is None
        assert document.error_message == "下载超时"
        assert document.downloaded_at is None

    def test_save_document_to_db_error_isolation(self):
        """测试数据库保存失败不抛出异常（错误隔离）"""
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)

        # 准备无效的测试数据（缺少必需字段）
        invalid_document_data = {
            "c_sdbh": "test_sdbh_003",
            # 缺少其他必需字段
        }

        download_result = (True, "/tmp/test_doc3.pdf", None)

        # 调用保存方法（不应该抛出异常）
        document_id = scraper._save_document_to_db(invalid_document_data, download_result)

        # 验证：应该返回 None（表示保存失败）
        assert document_id is None, "保存失败应该返回 None"

        # 验证：不应该有记录被创建
        count = CourtDocument.objects.filter(c_sdbh="test_sdbh_003").count()
        assert count == 0, "保存失败不应该创建记录"

    def test_save_documents_batch_success(self):
        """测试批量保存文书记录"""
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)

        # 准备测试数据
        documents_with_results = []
        for i in range(5):
            document_data = {
                "c_sdbh": f"batch_sdbh_{i}",
                "c_stbh": f"batch_stbh_{i}",
                "wjlj": f"https://example.com/batch_doc{i}.pdf",
                "c_wsbh": f"batch_wsbh_{i}",
                "c_wsmc": f"批量文书{i}",
                "c_fybh": f"batch_fybh_{i}",
                "c_fymc": "批量测试法院",
                "c_wjgs": "pdf",
                "dt_cjsj": "2024-01-01T00:00:00",
            }
            download_result = (True, f"/tmp/batch_doc{i}.pdf", None)
            documents_with_results.append((document_data, download_result))

        # 调用批量保存方法
        result = scraper._save_documents_batch(documents_with_results)

        # 验证：统计信息正确
        assert result["total"] == 5, "总数应该为 5"
        assert result["success"] == 5, "成功数应该为 5"
        assert result["failed"] == 0, "失败数应该为 0"
        assert len(result["document_ids"]) == 5, "应该返回 5 个文书 ID"

        # 验证：数据库中应该有 5 条记录
        count = CourtDocument.objects.filter(c_fymc="批量测试法院").count()
        assert count == 5, "数据库中应该有 5 条记录"

    def test_save_documents_batch_partial_failure(self):
        """测试批量保存时部分失败的情况"""
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)

        # 准备测试数据（包含一些无效数据）
        documents_with_results = []

        # 添加 3 个有效文书
        for i in range(3):
            document_data = {
                "c_sdbh": f"partial_sdbh_{i}",
                "c_stbh": f"partial_stbh_{i}",
                "wjlj": f"https://example.com/partial_doc{i}.pdf",
                "c_wsbh": f"partial_wsbh_{i}",
                "c_wsmc": f"部分文书{i}",
                "c_fybh": f"partial_fybh_{i}",
                "c_fymc": "部分测试法院",
                "c_wjgs": "pdf",
                "dt_cjsj": "2024-01-01T00:00:00",
            }
            download_result = (True, f"/tmp/partial_doc{i}.pdf", None)
            documents_with_results.append((document_data, download_result))

        # 添加 2 个无效文书（缺少必需字段）
        for i in range(3, 5):
            invalid_document_data = {
                "c_sdbh": f"partial_sdbh_{i}",
                # 缺少其他必需字段
            }
            download_result = (True, f"/tmp/partial_doc{i}.pdf", None)
            documents_with_results.append((invalid_document_data, download_result))

        # 调用批量保存方法
        result = scraper._save_documents_batch(documents_with_results)

        # 验证：统计信息正确
        assert result["total"] == 5, "总数应该为 5"
        assert result["success"] == 3, "成功数应该为 3"
        assert result["failed"] == 2, "失败数应该为 2"
        assert len(result["document_ids"]) == 3, "应该返回 3 个文书 ID"

        # 验证：数据库中应该只有 3 条有效记录
        count = CourtDocument.objects.filter(c_fymc="部分测试法院").count()
        assert count == 3, "数据库中应该只有 3 条有效记录"

    def test_save_documents_batch_all_failed(self):
        """测试批量保存时全部失败的情况"""
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)

        # 准备全部无效的测试数据
        documents_with_results = []
        for i in range(3):
            invalid_document_data = {
                "c_sdbh": f"failed_sdbh_{i}",
                # 缺少其他必需字段
            }
            download_result = (True, f"/tmp/failed_doc{i}.pdf", None)
            documents_with_results.append((invalid_document_data, download_result))

        # 调用批量保存方法（不应该抛出异常）
        result = scraper._save_documents_batch(documents_with_results)

        # 验证：统计信息正确
        assert result["total"] == 3, "总数应该为 3"
        assert result["success"] == 0, "成功数应该为 0"
        assert result["failed"] == 3, "失败数应该为 3"
        assert len(result["document_ids"]) == 0, "不应该返回任何文书 ID"

        # 验证：数据库中不应该有记录
        count = CourtDocument.objects.filter(c_sdbh__startswith="failed_sdbh_").count()
        assert count == 0, "数据库中不应该有记录"
