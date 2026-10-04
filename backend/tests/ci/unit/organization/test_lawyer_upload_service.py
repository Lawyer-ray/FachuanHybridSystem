"""LawyerUploadService 头像上传校验测试（安全审计：拒 svg 等可执行图片格式）。"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.exceptions import ValidationException
from apps.organization.models import LawFirm, Lawyer
from apps.organization.services.lawyer.upload import LawyerUploadService

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def lawyer(db: Any) -> Lawyer:
    firm = LawFirm.objects.create(name="头像上传测试律所")
    return Lawyer.objects.create_user(
        username="avatar_lawyer", password="testpass123", law_firm=firm  # pragma: allowlist secret
    )  # pragma: allowlist secret


@pytest.mark.django_db
def test_attach_avatar_rejects_svg(lawyer: Lawyer) -> None:
    """svg 可携带脚本且 /media/ 直链可执行，禁止入库。"""
    svg = SimpleUploadedFile("avatar.svg", b"<svg onload='alert(1)'/>", content_type="image/svg+xml")
    with pytest.raises(ValidationException, match="不支持的图片格式"):
        LawyerUploadService().attach_avatar(lawyer, svg)
    assert not lawyer.avatar.name


@pytest.mark.django_db
def test_attach_avatar_rejects_html(lawyer: Lawyer) -> None:
    html = SimpleUploadedFile("avatar.html", b"<html/>", content_type="text/html")
    with pytest.raises(ValidationException, match="不支持的图片格式"):
        LawyerUploadService().attach_avatar(lawyer, html)
    assert not lawyer.avatar.name


@pytest.mark.django_db
def test_attach_avatar_accepts_raster_images(lawyer: Lawyer, tmp_path: Any) -> None:
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        for name in ("a.jpg", "b.jpeg", "c.png", "d.webp"):
            img = SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")
            LawyerUploadService().attach_avatar(lawyer, img)
            assert lawyer.avatar.name, name


@pytest.mark.django_db
def test_attach_license_pdf_still_works(lawyer: Lawyer, tmp_path: Any) -> None:
    """license_pdf 原行为保持：pdf 正常入库。"""
    pdf = SimpleUploadedFile("license.pdf", b"%PDF-1.4 license", content_type="application/pdf")
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        LawyerUploadService().attach_license_pdf(lawyer, pdf)
    assert lawyer.license_pdf.name
