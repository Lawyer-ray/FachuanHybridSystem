"""
法院文书 Admin 属性测试

**Feature: court-document-api-optimization, Property 16: 搜索功能正确性**
验证需求: 5.5
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import RequestFactory
from django.utils import timezone
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from apps.automation.admin.scraper.court_document_admin import CourtDocumentAdmin
from apps.automation.models import CourtDocument, ScraperTask
from tests.factories.case_factories import CaseFactory

User = get_user_model()


# 策略：生成搜索条件
@st.composite
def search_term_strategy(draw):
    """生成搜索词"""
    return draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="中文测试"),
            min_size=1,
            max_size=20,
        )
    )


@st.composite
def court_document_with_search_data(draw):
    """生成包含可搜索数据的文书记录"""
    # 生成基础数据
    c_wsmc = draw(st.text(min_size=5, max_size=100))
    c_fymc = draw(st.text(min_size=3, max_size=50))
    c_wsbh = draw(st.text(min_size=5, max_size=30))
    c_sdbh = draw(st.text(min_size=5, max_size=30))

    return {
        "c_wsmc": c_wsmc,
        "c_fymc": c_fymc,
        "c_wsbh": c_wsbh,
        "c_sdbh": c_sdbh,
    }


@pytest.mark.django_db(transaction=True)
class TestCourtDocumentAdminSearchProperties:
    """测试 CourtDocument Admin 搜索功能的属性"""

    def setup_method(self):
        """设置测试环境"""
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = CourtDocumentAdmin(CourtDocument, self.site)

        # 创建测试用户
        self.user = User.objects.create_superuser(username="admin", email="admin@test.com", password="password")

        # 创建测试任务
        self.case = CaseFactory()
        self.task = ScraperTask.objects.create(  # type: ignore[misc]
            task_type="court_document", status="success", url="https://test.com", case=self.case
        )

    def teardown_method(self):
        """清理测试数据"""
        CourtDocument.objects.all().delete()
        ScraperTask.objects.all().delete()

    @given(search_data=court_document_with_search_data())
    @settings(max_examples=50, deadline=None)
    def test_search_by_document_name_returns_matching_records(self, search_data):
        """
        **Feature: court-document-api-optimization, Property 16: 搜索功能正确性**
        **Validates: Requirements 5.5**

        属性：对于任何搜索条件（文书名称），搜索结果应该只包含匹配该条件的记录
        """
        # 清理之前的数据
        CourtDocument.objects.all().delete()

        # 使用时区感知的 datetime
        now = timezone.now()

        # 创建文书记录（使用唯一标识符）
        import uuid

        unique_id = str(uuid.uuid4())[:8]

        document = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"{search_data['c_sdbh']}_{unique_id}",
            c_stbh=f"test_stbh_{unique_id}",
            wjlj="https://test.com/file.pdf",
            c_wsbh=f"{search_data['c_wsbh']}_{unique_id}",
            c_wsmc=search_data["c_wsmc"],
            c_fybh="test_fybh",
            c_fymc=search_data["c_fymc"],
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        # 创建不匹配的文书记录
        non_matching_document = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"different_sdbh_{unique_id}",
            c_stbh=f"different_stbh_{unique_id}",
            wjlj="https://test.com/file2.pdf",
            c_wsbh=f"different_wsbh_{unique_id}",
            c_wsmc="完全不同的文书名称",
            c_fybh="different_fybh",
            c_fymc="完全不同的法院",
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        # 创建请求
        request = self.factory.get("/", {"q": search_data["c_wsmc"]})
        request.user = self.user

        # 获取搜索结果
        changelist = self.admin.get_changelist_instance(request)
        queryset = changelist.get_queryset(request)

        # 验证：搜索结果应该包含匹配的记录
        assert document in queryset, "搜索结果应该包含匹配文书名称的记录"

        # 验证：搜索结果不应该包含不匹配的记录
        assert non_matching_document not in queryset, "搜索结果不应该包含不匹配的记录"

    @given(search_data=court_document_with_search_data())
    @settings(max_examples=50, deadline=None)
    def test_search_by_court_name_returns_matching_records(self, search_data):
        """
        **Feature: court-document-api-optimization, Property 16: 搜索功能正确性**
        **Validates: Requirements 5.5**

        属性：对于任何搜索条件（法院名称），搜索结果应该只包含匹配该条件的记录
        """
        # 清理之前的数据
        CourtDocument.objects.all().delete()

        # 使用时区感知的 datetime
        now = timezone.now()

        # 创建文书记录（使用唯一标识符）
        import uuid

        unique_id = str(uuid.uuid4())[:8]

        document = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"{search_data['c_sdbh']}_{unique_id}",
            c_stbh=f"test_stbh_{unique_id}",
            wjlj="https://test.com/file.pdf",
            c_wsbh=f"{search_data['c_wsbh']}_{unique_id}",
            c_wsmc=search_data["c_wsmc"],
            c_fybh="test_fybh",
            c_fymc=search_data["c_fymc"],
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        # 创建不匹配的文书记录
        non_matching_document = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"different_sdbh_{unique_id}",
            c_stbh=f"different_stbh_{unique_id}",
            wjlj="https://test.com/file2.pdf",
            c_wsbh=f"different_wsbh_{unique_id}",
            c_wsmc="完全不同的文书名称",
            c_fybh="different_fybh",
            c_fymc="完全不同的法院",
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        # 创建请求
        request = self.factory.get("/", {"q": search_data["c_fymc"]})
        request.user = self.user

        # 获取搜索结果
        changelist = self.admin.get_changelist_instance(request)
        queryset = changelist.get_queryset(request)

        # 验证：搜索结果应该包含匹配的记录
        assert document in queryset, "搜索结果应该包含匹配法院名称的记录"

        # 验证：搜索结果不应该包含不匹配的记录
        assert non_matching_document not in queryset, "搜索结果不应该包含不匹配的记录"

    @given(search_data=court_document_with_search_data())
    @settings(max_examples=50, deadline=None)
    def test_search_by_document_number_returns_matching_records(self, search_data):
        """
        **Feature: court-document-api-optimization, Property 16: 搜索功能正确性**
        **Validates: Requirements 5.5**

        属性：对于任何搜索条件（文书编号），搜索结果应该只包含匹配该条件的记录
        """
        # 清理之前的数据
        CourtDocument.objects.all().delete()

        # 使用时区感知的 datetime
        now = timezone.now()

        # 创建文书记录（使用唯一标识符）
        import uuid

        unique_id = str(uuid.uuid4())[:8]

        document = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"{search_data['c_sdbh']}_{unique_id}",
            c_stbh=f"test_stbh_{unique_id}",
            wjlj="https://test.com/file.pdf",
            c_wsbh=f"{search_data['c_wsbh']}_{unique_id}",
            c_wsmc=search_data["c_wsmc"],
            c_fybh="test_fybh",
            c_fymc=search_data["c_fymc"],
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        # 创建不匹配的文书记录
        non_matching_document = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"different_sdbh_{unique_id}",
            c_stbh=f"different_stbh_{unique_id}",
            wjlj="https://test.com/file2.pdf",
            c_wsbh=f"different_wsbh_{unique_id}",
            c_wsmc="完全不同的文书名称",
            c_fybh="different_fybh",
            c_fymc="完全不同的法院",
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        # 创建请求
        request = self.factory.get("/", {"q": f"{search_data['c_wsbh']}_{unique_id}"})
        request.user = self.user

        # 获取搜索结果
        changelist = self.admin.get_changelist_instance(request)
        queryset = changelist.get_queryset(request)

        # 验证：搜索结果应该包含匹配的记录
        assert document in queryset, "搜索结果应该包含匹配文书编号的记录"

        # 验证：搜索结果不应该包含不匹配的记录
        assert non_matching_document not in queryset, "搜索结果不应该包含不匹配的记录"

    @given(search_data=court_document_with_search_data())
    @settings(max_examples=30, deadline=None)
    def test_empty_search_returns_all_records(self, search_data):
        """
        **Feature: court-document-api-optimization, Property 16: 搜索功能正确性**
        **Validates: Requirements 5.5**

        属性：空搜索条件应该返回所有记录
        """
        # 清理之前的数据
        CourtDocument.objects.all().delete()

        # 使用时区感知的 datetime
        now = timezone.now()

        # 创建多个文书记录（使用唯一标识符）
        import uuid

        unique_id = str(uuid.uuid4())[:8]

        document1 = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"{search_data['c_sdbh']}_{unique_id}_1",
            c_stbh=f"test_stbh_{unique_id}_1",
            wjlj="https://test.com/file1.pdf",
            c_wsbh=f"{search_data['c_wsbh']}_{unique_id}_1",
            c_wsmc=search_data["c_wsmc"],
            c_fybh="test_fybh",
            c_fymc=search_data["c_fymc"],
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        document2 = CourtDocument.objects.create(  # type: ignore[misc]
            scraper_task=self.task,
            case=self.case,
            c_sdbh=f"different_sdbh_{unique_id}_2",
            c_stbh=f"test_stbh_{unique_id}_2",
            wjlj="https://test.com/file2.pdf",
            c_wsbh=f"different_wsbh_{unique_id}_2",
            c_wsmc="不同的文书",
            c_fybh="different_fybh",
            c_fymc="不同的法院",
            c_wjgs="pdf",
            dt_cjsj=now,
            download_status="success",
        )

        # 创建空搜索请求
        request = self.factory.get("/", {"q": ""})
        request.user = self.user

        # 获取搜索结果
        changelist = self.admin.get_changelist_instance(request)
        queryset = changelist.get_queryset(request)

        # 验证：空搜索应该返回所有记录
        assert document1 in queryset, "空搜索应该包含所有记录"
        assert document2 in queryset, "空搜索应该包含所有记录"
        assert queryset.count() >= 2, "空搜索应该返回所有记录"
