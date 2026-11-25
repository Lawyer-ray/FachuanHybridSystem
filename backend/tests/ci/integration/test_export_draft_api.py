"""`POST /pdf-splitting/export-draft` 的 HTTP 契约。

单元测试（`tests/ci/unit/pdf_splitting/test_export_draft.py`）覆盖切页/打包逻辑；
这里补只有走真实请求才证得了的三件事：

1. multipart 解析：`files` 走 `request.FILES.getlist`、`spec` 走 `request.POST`；
2. 响应是 zip（Content-Type + 能被 zipfile 打开），包内条目名按段名给出；
3. `X-Export-Skipped` 头真的回给了调用方（前端靠它提示「N 段没导出」）。
"""

from __future__ import annotations

import io
import json
import zipfile
from urllib.parse import quote

import pymupdf as fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


def _pdf(pages: int = 3) -> bytes:
    doc = fitz.open()
    try:
        for no in range(1, pages + 1):
            doc.new_page(width=595, height=842).insert_text((72, 72), f"PAGE-{no}")
        return doc.tobytes()  # type: ignore[no-any-return]
    finally:
        doc.close()


@pytest.mark.django_db
def test_export_draft_returns_zip(authenticated_client: object) -> None:
    spec = {"segments": [{"name": "起诉状", "part_index": 0, "page_start": 1, "page_end": 2}]}
    # name 是 **query** 参数（前端也是拼在 URL 上）；放 body 里 Ninja 不会读
    resp = authenticated_client.post(  # type: ignore[attr-defined]
        f"/api/v1/pdf-splitting/export-draft?name={quote('某某案-起诉材料')}",
        data={
            "files": SimpleUploadedFile("part_0.pdf", _pdf(3), content_type="application/pdf"),
            "spec": json.dumps(spec),
        },
    )
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/zip"
    # 中文名按 RFC 5987 百分号编码（filename*）；断言解码后的名字更稳
    assert quote("某某案-起诉材料.zip") in resp["Content-Disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert archive.namelist() == ["01-起诉状.pdf"]
        doc = fitz.open(stream=archive.read("01-起诉状.pdf"), filetype="pdf")
        try:
            assert doc.page_count == 2
            assert "PAGE-1" in doc.load_page(0).get_text()
        finally:
            doc.close()


@pytest.mark.django_db
def test_export_draft_reports_skipped_segments(authenticated_client: object) -> None:
    """越界段被跳过时，数量必须经响应头告诉前端（不静默少几份）。"""
    spec = {
        "segments": [
            {"name": "正常", "part_index": 0, "page_start": 1, "page_end": 1},
            {"name": "越界", "part_index": 0, "page_start": 1, "page_end": 99},
        ]
    }
    resp = authenticated_client.post(  # type: ignore[attr-defined]
        "/api/v1/pdf-splitting/export-draft",
        data={
            "files": SimpleUploadedFile("part_0.pdf", _pdf(2), content_type="application/pdf"),
            "spec": json.dumps(spec),
        },
    )
    assert resp.status_code == 200
    assert resp["X-Export-Skipped"] == "1"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert archive.namelist() == ["01-正常.pdf"]


@pytest.mark.django_db
def test_export_draft_rejects_bad_spec(authenticated_client: object) -> None:
    resp = authenticated_client.post(  # type: ignore[attr-defined]
        "/api/v1/pdf-splitting/export-draft",
        data={
            "files": SimpleUploadedFile("part_0.pdf", _pdf(1), content_type="application/pdf"),
            "spec": "{}",
        },
    )
    assert resp.status_code == 400
    # 不是「随便 400」：要能按 code/errors 区分「spec 里没有分段」，
    # 前端据此提示而不是报「导出失败」
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == "VALIDATION_ERROR"
    assert "segments" in (body["errors"] or {})
