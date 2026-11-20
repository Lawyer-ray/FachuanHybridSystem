"""PDF 自动分段：单段 pdf / 单段 md / 多选与整包 zip 下载。

## 这些用例存在的原因

需求是「打包下载已经转好的 Markdown 以及分好段的 pdf，可以单个下载、多选下载，
也可以整包下载」。三条容易悄悄坏掉、且坏了律师看不出来的规则，全部钉在这里：

* **每个 pdf 必须配一个同名 md** —— 旧整包只有 pdf；漏掉配对的失败模式是
  「包里看着有 md，但某几段没有」，而界面上不会报任何错；
* **未选中的段不许渲** —— 多选下载如果仍然把整卷渲一遍，勾 3 段要等 93 页；
* **ids 里非法/不属于本任务的段必须 400 并点名** —— 静默跳过等于让律师以为
  「选中的都打进去了」，整包悄悄缺页是卷宗类工具最坏的失败模式。

测试 PDF 由 pymupdf 现场生成（每页自带 `PAGE-n` 文本），切完按文本就能验出
切的是哪几页；MEDIA_ROOT 隔离到 tmp_path，因为打包真的会读写任务目录。
"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf as fitz
import pytest
from django.test import RequestFactory

from apps.core.exceptions import NotFoundError, ValidationException
from apps.pdf_splitting.api.pdf_splitting_api import (
    _parse_segment_ids,
    get_pdf_split_download,
    get_pdf_split_segment_markdown,
    get_pdf_split_segment_pdf,
    router,
)
from apps.pdf_splitting.models import (
    PdfSplitJob,
    PdfSplitJobStatus,
    PdfSplitReviewFlag,
    PdfSplitSegment,
    PdfSplitSegmentType,
    PdfSplitSourceType,
)
from apps.pdf_splitting.services.split import PdfSplitService
from apps.pdf_splitting.services.split import service as split_service_module
from apps.pdf_splitting.services.storage import PdfSplitStorage
from apps.testing.factories import LawyerFactory

pytestmark = pytest.mark.django_db

_factory = RequestFactory()

PAGE_COUNT = 6


# ---------------------------------------------------------------- helpers


def _build_pdf(page_count: int = PAGE_COUNT) -> bytes:
    """每页自带页号的 PDF：切完后按文本就能验出切的是哪几页。"""
    doc = fitz.open()
    try:
        for no in range(1, page_count + 1):
            page = doc.new_page()
            page.insert_text((72, 72), f"PAGE-{no}")
        return doc.tobytes()  # type: ignore[no-any-return]
    finally:
        doc.close()


def _request(user: Any = None) -> Any:
    request = _factory.get("/")
    if user is not None:
        request.user = user
    return request


def _job(*, pages: int = PAGE_COUNT, created_by: Any = None) -> PdfSplitJob:
    job = PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="卷宗示例.pdf",
        status=PdfSplitJobStatus.REVIEW_REQUIRED,
        total_pages=pages,
        created_by=created_by,
    )
    storage = PdfSplitStorage(job.id)
    storage.ensure_dirs()
    storage.source_pdf_path.write_bytes(_build_pdf(pages))
    return job


def _segment(
    job: PdfSplitJob,
    *,
    order: int,
    page_start: int,
    page_end: int,
    filename: str,
    segment_type: str = PdfSplitSegmentType.COMPLAINT,
) -> PdfSplitSegment:
    return PdfSplitSegment.objects.create(
        job=job,
        order=order,
        page_start=page_start,
        page_end=page_end,
        segment_type=segment_type,
        filename=filename,
        confidence=1.0,
        source_method="rule",
        review_flag=PdfSplitReviewFlag.NORMAL,
    )


DEFAULT_SEGMENTS: tuple[tuple[int, int, int, str], ...] = (
    (1, 1, 2, "起诉状.pdf"),
    (2, 3, 4, "证据目录.pdf"),
    (3, 5, 6, "证据目录.pdf"),  # 与上一段同名：zip 里靠 order 前缀区分，不能被覆盖
)


def _three_segments(job: PdfSplitJob) -> list[PdfSplitSegment]:
    return [
        _segment(job, order=order, page_start=start, page_end=end, filename=name)
        for order, start, end, name in DEFAULT_SEGMENTS
    ]


def _write_markdown(job: PdfSplitJob, *, orders: list[int] | None = None) -> dict[int, str]:
    """写 segments_md.json（下载侧按 order 取段正文的唯一来源）。"""
    payload = []
    texts: dict[int, str] = {}
    for order, start, end, name in DEFAULT_SEGMENTS:
        if orders is not None and order not in orders:
            continue
        text = f"# {name.removesuffix('.pdf')}\n\n第 {start}-{end} 页正文\n"
        texts[order] = text
        payload.append(
            {
                "order": order,
                "page_start": start,
                "page_end": end,
                "markdown": text,
                "page_spans": [],
                "positioned": [],
            }
        )
    PdfSplitStorage(job.id).write_json(PdfSplitStorage(job.id).segments_md_path, payload)
    return texts


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """打包会真的读写任务目录（源 pdf / segments_md.json / 历史整包），必须隔离。"""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _zip_names(content: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.namelist()


def _zip_entry(content: bytes, name: str) -> bytes:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read(name)


# ---------------------------------------------------------------- ids 解析


class TestParseSegmentIds:
    def test_empty_means_whole_package(self) -> None:
        assert _parse_segment_ids("") is None
        assert _parse_segment_ids("   ") is None

    def test_comma_separated_numbers(self) -> None:
        assert _parse_segment_ids("12,15") == [12, 15]
        assert _parse_segment_ids(" 7 ") == [7]
        assert _parse_segment_ids("3,3") == [3, 3]  # 去重交给 Service，解析层如实透出

    @pytest.mark.parametrize("raw", ["abc", "1,,2", "1,", "1;2", "1.5", "-3", "１２", "1 2"])
    def test_rejects_non_numeric_tokens(self, raw: str) -> None:
        """防注入 + 防空 token：只接受 ASCII 数字，其余整体 400 并点名。"""
        with pytest.raises(ValidationException) as excinfo:
            _parse_segment_ids(raw)

        assert "ids" in dict(excinfo.value.errors)


# ---------------------------------------------------------------- 单段下载


class TestSingleSegmentDownload:
    def test_pdf_stream_is_the_right_pages(self) -> None:
        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)

        response = get_pdf_split_segment_pdf(_request(), job.id, segments[1].id)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        # RFC 5987：中文名百分号编码进 filename*，浏览器按 UTF-8 还原
        assert "attachment" in response["Content-Disposition"]
        assert "%E8%AF%81%E6%8D%AE%E7%9B%AE%E5%BD%95.pdf" in response["Content-Disposition"]
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            assert [page.get_text().strip() for page in doc] == ["PAGE-3", "PAGE-4"]

    def test_markdown_body_matches_persisted_product(self) -> None:
        job = _job()
        segments = _three_segments(job)
        texts = _write_markdown(job)

        response = get_pdf_split_segment_markdown(_request(), job.id, segments[0].id)

        assert response.status_code == 200
        assert response["Content-Type"] == "text/markdown; charset=utf-8"
        assert response.content.decode("utf-8") == texts[1]
        assert "%E8%B5%B7%E8%AF%89%E7%8A%B6.md" in response["Content-Disposition"]

    def test_filename_is_sanitized(self) -> None:
        """文件名只来自数据库字段 + 安全化函数：路径穿越被削平。"""
        job = _job()
        segment = _segment(job, order=1, page_start=1, page_end=2, filename="../../etc/起诉状.pdf")

        content, filename = PdfSplitService().build_download_pdf(job, segment.id)

        assert filename == "起诉状.pdf"
        assert content.startswith(b"%PDF")

    def test_missing_markdown_raises_not_found(self) -> None:
        job = _job()
        segments = _three_segments(job)  # 故意不写 segments_md.json

        with pytest.raises(NotFoundError) as excinfo:
            PdfSplitService().build_download_markdown(job, segments[0].id)

        assert excinfo.value.code == "PDF_SPLIT_SEGMENT_MD_NOT_FOUND"

    def test_empty_markdown_entry_is_treated_as_missing(self) -> None:
        """空 md 回 404 而不是回空文件：空文件看起来像「下载成功但没内容」。"""
        job = _job()
        segments = _three_segments(job)
        storage = PdfSplitStorage(job.id)
        storage.write_json(storage.segments_md_path, [{"order": 1, "markdown": "   "}])

        with pytest.raises(NotFoundError):
            PdfSplitService().build_download_markdown(job, segments[0].id)

    def test_foreign_segment_is_not_found(self) -> None:
        job = _job()
        other_job = _job()
        foreign = _segment(other_job, order=1, page_start=1, page_end=2, filename="别人的材料.pdf")

        with pytest.raises(NotFoundError) as excinfo:
            PdfSplitService().build_download_pdf(job, foreign.id)

        assert excinfo.value.code == "PDF_SPLIT_SEGMENT_NOT_FOUND"

    def test_other_users_job_is_not_found(self) -> None:
        """鉴权沿用既有装配：靠 get_job(user=...) 做属主校验（与 /download 一致）。"""
        job = _job(created_by=LawyerFactory())
        segments = _three_segments(job)

        with pytest.raises(NotFoundError):
            get_pdf_split_segment_pdf(_request(LawyerFactory()), job.id, segments[0].id)

    def test_missing_source_pdf_raises_not_found(self) -> None:
        job = _job()
        segments = _three_segments(job)
        PdfSplitStorage(job.id).source_pdf_path.unlink()

        with pytest.raises(NotFoundError) as excinfo:
            PdfSplitService().build_download_pdf(job, segments[0].id)

        assert excinfo.value.code == "PDF_SPLIT_SOURCE_MISSING"


# ---------------------------------------------------------------- 整包 / 多选


class TestZipDownload:
    def test_whole_package_pairs_every_pdf_with_markdown(self) -> None:
        job = _job()
        _three_segments(job)
        texts = _write_markdown(job)

        content, filename = PdfSplitService().build_download_zip(job=job)

        assert filename == "split_result.zip"
        assert _zip_names(content) == [
            "01_起诉状.pdf",
            "01_起诉状.md",
            "02_证据目录.pdf",
            "02_证据目录.md",
            "03_证据目录.pdf",
            "03_证据目录.md",
        ]
        # 平铺：不带任何目录项
        assert all("/" not in name for name in _zip_names(content))
        assert _zip_entry(content, "02_证据目录.md").decode("utf-8") == texts[2]
        assert _zip_entry(content, "03_证据目录.pdf").startswith(b"%PDF")

    def test_selected_ids_package_only_contains_selection(self) -> None:
        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)

        content, filename = PdfSplitService().build_download_zip(job=job, segment_ids=[segments[2].id, segments[0].id])

        assert filename == "split_result_selected.zip"
        # 请求顺序 3,1 → 包内仍按卷宗顺序排
        assert _zip_names(content) == [
            "01_起诉状.pdf",
            "01_起诉状.md",
            "03_证据目录.pdf",
            "03_证据目录.md",
        ]

    def test_unselected_segments_are_not_rendered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """性能红线：整卷 93 页时，勾 3 段不能把 93 页都渲一遍。"""
        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)
        rendered: list[tuple[int, int]] = []
        real = split_service_module.export_segment_pdf

        def _spy(source_doc: Any, page_start: int, page_end: int) -> bytes:
            rendered.append((page_start, page_end))
            return real(source_doc, page_start, page_end)

        monkeypatch.setattr(split_service_module, "export_segment_pdf", _spy)

        PdfSplitService().build_download_zip(job=job, segment_ids=[segments[2].id])

        assert rendered == [(5, 6)]

    def test_duplicate_ids_are_deduplicated(self) -> None:
        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)

        content, _ = PdfSplitService().build_download_zip(job=job, segment_ids=[segments[0].id, segments[0].id])

        assert _zip_names(content) == ["01_起诉状.pdf", "01_起诉状.md"]

    def test_missing_markdown_degrades_to_pdf_only(self, caplog: pytest.LogCaptureFixture) -> None:
        """某段缺 md → 只放 pdf + warning，整包不许失败（md 是副产物）。"""
        job = _job()
        _three_segments(job)
        _write_markdown(job, orders=[1, 3])  # 第 2 段故意没有 md 条目

        with caplog.at_level(logging.WARNING, logger="apps.pdf_splitting"):
            content, _ = PdfSplitService().build_download_zip(job=job)

        assert _zip_names(content) == [
            "01_起诉状.pdf",
            "01_起诉状.md",
            "02_证据目录.pdf",
            "03_证据目录.pdf",
            "03_证据目录.md",
        ]
        assert "pdf_split_export_markdown_missing" in caplog.text

    def test_unknown_id_in_selection_is_rejected_with_id_named(self) -> None:
        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)
        missing_id = max(segment.id for segment in segments) + 1000

        with pytest.raises(ValidationException) as excinfo:
            PdfSplitService().build_download_zip(job=job, segment_ids=[segments[0].id, missing_id])

        assert str(missing_id) in str(excinfo.value.message)
        assert dict(excinfo.value.errors)["ids"] == [missing_id]

    def test_foreign_job_segment_id_is_rejected(self) -> None:
        job = _job()
        _three_segments(job)
        _write_markdown(job)
        other_job = _job()
        foreign = _segment(other_job, order=1, page_start=1, page_end=2, filename="别人的材料.pdf")

        with pytest.raises(ValidationException) as excinfo:
            get_pdf_split_download(_request(), job.id, ids=str(foreign.id))

        assert str(foreign.id) in str(excinfo.value.message)

    def test_empty_segment_list_returns_no_package(self) -> None:
        """没段可打 → Service 回 None，端点沿用旧契约：404 + **空**响应体。"""
        job = _job()

        assert PdfSplitService().build_download_zip(job=job) is None

        response = get_pdf_split_download(_request(), job.id)
        assert response.status_code == 404
        assert response.content == b""

    def test_stale_persisted_zip_is_not_served_for_whole_package(self) -> None:
        """整包必须现算：上线前导出的 zip 没有 md，直接发出去就是「整包缺 md」。"""
        job = _job()
        _three_segments(job)
        _write_markdown(job)
        storage = PdfSplitStorage(job.id)
        stale = BytesIO()
        with zipfile.ZipFile(stale, "w") as archive:
            archive.writestr("起诉状.pdf", b"%PDF-stale")
        storage.export_zip_path.write_bytes(stale.getvalue())

        content, _ = PdfSplitService().build_download_zip(job=job)

        assert "01_起诉状.md" in _zip_names(content)
        assert "起诉状.pdf" not in _zip_names(content)

    def test_source_missing_whole_package_falls_back_to_persisted_zip(self, caplog: pytest.LogCaptureFixture) -> None:
        """源 PDF 被清理但历史整包还在：整包回旧包（不把 200 变成 404）。"""
        job = _job()
        _three_segments(job)
        storage = PdfSplitStorage(job.id)
        storage.source_pdf_path.unlink()
        stale = BytesIO()
        with zipfile.ZipFile(stale, "w") as archive:
            archive.writestr("起诉状.pdf", b"%PDF-stale")
        storage.export_zip_path.write_bytes(stale.getvalue())

        with caplog.at_level(logging.WARNING, logger="apps.pdf_splitting"):
            content, _ = PdfSplitService().build_download_zip(job=job)

        assert _zip_names(content) == ["起诉状.pdf"]
        assert "pdf_split_download_source_missing" in caplog.text

    def test_source_missing_selection_raises_instead_of_leaking_whole_package(self) -> None:
        """多选做不了同样的降级：拿整包当「只勾了几段」返回比报错更糟。"""
        job = _job()
        segments = _three_segments(job)
        storage = PdfSplitStorage(job.id)
        storage.source_pdf_path.unlink()
        storage.export_zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

        with pytest.raises(NotFoundError) as excinfo:
            PdfSplitService().build_download_zip(job=job, segment_ids=[segments[0].id])

        assert excinfo.value.code == "PDF_SPLIT_SOURCE_MISSING"


# ---------------------------------------------------------------- 端点装配


class TestDownloadEndpoints:
    def test_download_without_ids_stays_whole_package(self) -> None:
        """向后兼容：旧整包按钮不带 ids，仍是 200 zip（包里多了 md）。"""
        job = _job()
        _three_segments(job)
        _write_markdown(job)

        response = get_pdf_split_download(_request(), job.id)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/zip"
        assert "split_result.zip" in response["Content-Disposition"]
        assert len(_zip_names(response.content)) == 6

    def test_download_with_ids_returns_selection(self) -> None:
        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)
        ids = ",".join(str(segment.id) for segment in segments[:2])

        response = get_pdf_split_download(_request(), job.id, ids=ids)

        assert response.status_code == 200
        assert sorted(_zip_names(response.content)) == [
            "01_起诉状.md",
            "01_起诉状.pdf",
            "02_证据目录.md",
            "02_证据目录.pdf",
        ]

    def test_download_rejects_garbage_ids_before_touching_storage(self) -> None:
        job = _job()
        _three_segments(job)

        with pytest.raises(ValidationException):
            get_pdf_split_download(_request(), job.id, ids="1;drop")

    def test_new_routes_live_on_the_authenticated_router(self) -> None:
        """三条新路由挂在同一个 router 上：鉴权由 api.py 装配的 JWTOrSessionAuth 统一兜。

        （router 级别的 auth 在 ``apiSystem/apiSystem/api.py`` 的 add_router 里给，
        所以「和既有 /download 同 router」就是「同一套鉴权」的直接证据。）
        """
        paths = set(router.path_operations.keys())

        assert "/jobs/{job_id}/segments/{segment_id}/pdf" in paths
        assert "/jobs/{job_id}/segments/{segment_id}/md" in paths
        assert "/jobs/{job_id}/download" in paths


# ---------------------------------------------------------------- 走 HTTP 的端到端契约


class TestDownloadOverHttp:
    """真打 URL：验证路由前缀、query 参数解析、响应头与鉴权装配（不只看函数返回）。

    函数级用例覆盖业务规则；这一组覆盖「线上真正走的那条路」——Ninja 的 query
    参数绑定、`/api/v1/pdf-splitting` 前缀、以及未登录必须被挡下。三者任一坏掉，
    函数级用例都是绿的。
    """

    def test_segment_pdf_and_md_over_http(self, authenticated_client: Any) -> None:
        job = _job()
        segments = _three_segments(job)
        texts = _write_markdown(job)
        segment = segments[0]

        pdf_resp = authenticated_client.get(f"/api/v1/pdf-splitting/jobs/{job.id}/segments/{segment.id}/pdf")
        md_resp = authenticated_client.get(f"/api/v1/pdf-splitting/jobs/{job.id}/segments/{segment.id}/md")

        assert pdf_resp.status_code == 200
        assert pdf_resp["Content-Type"] == "application/pdf"
        assert "filename*=UTF-8''" in pdf_resp["Content-Disposition"]
        assert md_resp.status_code == 200
        assert md_resp["Content-Type"] == "text/markdown; charset=utf-8"
        assert md_resp.content.decode("utf-8") == texts[1]

    def test_download_ids_query_param_over_http(self, authenticated_client: Any) -> None:
        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)

        resp = authenticated_client.get(
            f"/api/v1/pdf-splitting/jobs/{job.id}/download?ids={segments[0].id},{segments[1].id}"
        )

        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/zip"
        assert sorted(_zip_names(resp.content)) == [
            "01_起诉状.md",
            "01_起诉状.pdf",
            "02_证据目录.md",
            "02_证据目录.pdf",
        ]

    def test_download_rejects_bad_ids_over_http(self, authenticated_client: Any) -> None:
        job = _job()
        _three_segments(job)

        resp = authenticated_client.get(f"/api/v1/pdf-splitting/jobs/{job.id}/download?ids=abc")

        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_anonymous_cannot_download(self) -> None:
        """鉴权与既有 /download 一致（JWTOrSessionAuth）：未登录拿不到任何产物。"""
        from django.test import Client

        job = _job()
        segments = _three_segments(job)
        _write_markdown(job)
        client = Client()

        for url in (
            f"/api/v1/pdf-splitting/jobs/{job.id}/segments/{segments[0].id}/pdf",
            f"/api/v1/pdf-splitting/jobs/{job.id}/segments/{segments[0].id}/md",
            f"/api/v1/pdf-splitting/jobs/{job.id}/download",
        ):
            resp = client.get(url)
            assert resp.status_code in {401, 403}, url
            # 只断状态码不够：还要确认响应体里没有产物内容（未登录不能拿到任何字节）
            assert b"%PDF" not in resp.content, url
