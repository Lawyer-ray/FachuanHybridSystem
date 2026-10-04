"""安全审计第4轮：pdf_splitting 越权修复回归测试。

覆盖：
1. get_job 按 created_by 属主过滤（他人 job 按不存在处理，管理员全量）
2. create 端点提交 source_path 收敛为管理员专用（file 上传不受影响）
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from django.test import RequestFactory

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.pdf_splitting.api.pdf_splitting_api import create_pdf_split_job, get_pdf_split_job
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType
from apps.pdf_splitting.services.job_service import PdfSplitJobService
from apps.testing.factories import LawyerFactory

_factory = RequestFactory()


def _request(user: Any):
    request = _factory.post("/")
    request.user = user
    return request


def _make_job(created_by: Any) -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="doc.pdf",
        status=PdfSplitJobStatus.PENDING,
        total_pages=1,
        created_by=created_by,
    )


class TestGetJobOwnership:
    @pytest.mark.django_db
    def test_other_users_job_treated_as_not_found(self) -> None:
        owner = LawyerFactory()
        stranger = LawyerFactory()
        job = _make_job(created_by=owner)

        with pytest.raises(NotFoundError):
            PdfSplitJobService().get_job(job.id, user=stranger)

    @pytest.mark.django_db
    def test_owner_and_admin_can_read(self) -> None:
        owner = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        job = _make_job(created_by=owner)

        assert PdfSplitJobService().get_job(job.id, user=owner).id == job.id
        assert PdfSplitJobService().get_job(job.id, user=admin).id == job.id

    @pytest.mark.django_db
    def test_internal_call_without_user_unfiltered(self) -> None:
        """后台任务执行等内部调用（不传 user）不做属主过滤。"""
        owner = LawyerFactory()
        job = _make_job(created_by=owner)

        assert PdfSplitJobService().get_job(job.id).id == job.id

    @pytest.mark.django_db
    def test_api_get_job_passes_user(self) -> None:
        """API 端点必须把请求用户传给 get_job（属主校验）。"""
        stranger = LawyerFactory()
        job = _make_job(created_by=LawyerFactory())
        request = _request(stranger)

        with pytest.raises(NotFoundError):
            get_pdf_split_job(request, job.id)


class TestCreateSourcePathAdminOnly:
    @pytest.mark.django_db
    def test_source_path_denied_for_normal_user(self) -> None:
        request = _request(LawyerFactory())
        with pytest.raises(PermissionDenied):
            create_pdf_split_job(request, file=None, source_path="/etc/passwd")

    @pytest.mark.django_db
    def test_source_path_admin_passes_gate(self, tmp_path) -> None:
        from django.test import override_settings

        request = _request(LawyerFactory(is_admin=True))
        # MEDIA_ROOT 重定向到临时目录，避免服务层 ensure_dirs 在真实 media 落目录
        with override_settings(MEDIA_ROOT=tmp_path):
            # 管理员通过权限门后进入服务层（路径不存在 → ValidationException，
            # 证明门在前、未被绕过）
            with pytest.raises(ValidationException):
                create_pdf_split_job(request, file=None, source_path="/nonexistent/path/x.pdf")
