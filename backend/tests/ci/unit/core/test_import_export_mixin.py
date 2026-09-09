"""apps/core/admin/mixins/import_export_mixin.py 文件解压逻辑单元测试。

聚焦校验：
- 正常 files/ 成员走 default_storage.save() 还原；
- Zip Slip 恶意路径（..）被拒绝且不落盘；
- 已存在的 storage 键不会覆盖（保持原语义）。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.core.admin.mixins.import_export_mixin import AdminImportExportMixin


@pytest.fixture
def mixin() -> AdminImportExportMixin:
    return AdminImportExportMixin()


def _make_zip(members: list[tuple[str, bytes]]) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in members:
            zf.writestr(name, content)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_extract_files_saves_through_default_storage(mixin: AdminImportExportMixin) -> None:
    zf = _make_zip([("files/client_docs/a.pdf", b"pdf-bytes")])

    with patch(
        "apps.core.services.storage_service._get_media_root",
        return_value=str(Path("/fake/media").resolve()),
    ), patch("django.core.files.storage.default_storage.save") as mock_save, patch(
        "django.core.files.storage.default_storage.exists", return_value=False
    ) as mock_exists:
        mixin._extract_files(zf)

    mock_exists.assert_called_once_with("client_docs/a.pdf")
    mock_save.assert_called_once()
    name_arg, file_arg = mock_save.call_args[0]
    assert name_arg == "client_docs/a.pdf"
    assert file_arg.read() == b"pdf-bytes"


def test_extract_files_skips_existing_storage_key(mixin: AdminImportExportMixin) -> None:
    zf = _make_zip([("files/client_docs/a.pdf", b"pdf-bytes")])

    with patch(
        "apps.core.services.storage_service._get_media_root",
        return_value=str(Path("/fake/media").resolve()),
    ), patch("django.core.files.storage.default_storage.save") as mock_save, patch(
        "django.core.files.storage.default_storage.exists", return_value=True
    ):
        mixin._extract_files(zf)

    mock_save.assert_not_called()


def test_extract_files_rejects_zip_slip(mixin: AdminImportExportMixin) -> None:
    zf = _make_zip([("files/../../etc/passwd", b"evil")])

    with patch(
        "apps.core.services.storage_service._get_media_root",
        return_value=str(Path("/fake/media").resolve()),
    ), patch("django.core.files.storage.default_storage.save") as mock_save:
        mixin._extract_files(zf)

    mock_save.assert_not_called()
