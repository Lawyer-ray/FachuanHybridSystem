"""劳动仲裁文书解析服务单元测试。

锁定 parse_arbitration_document 的核心契约：
- 状态机：PROCESSING → DONE / FAILED，backend 记录，错误信息截断写回；
- 页序：按 page_index 升序送 OCR，文本/Markdown 按页拼接；
- 临时文件按需下载并清理；
- 无图片 / 解析异常的失败兜底。

OCR 后端与 Doxify 清洗均打桩，保证测试确定性。
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.labor_arbitration.models import (
    ArbitrationDocument,
    ArbitrationDocumentImage,
    ArbitrationDocumentSource,
    DocumentCrawlStatus,
    ParseStatus,
)
from apps.labor_arbitration.services import parsing_service


@pytest.fixture
def source(db: Any) -> ArbitrationDocumentSource:
    return ArbitrationDocumentSource.objects.create(name="测试来源", list_url="https://fsrsj.foshan.gov.cn/test-list")


@pytest.fixture
def doc(source: ArbitrationDocumentSource) -> ArbitrationDocument:
    return ArbitrationDocument.objects.create(source=source, title="仲裁裁决书", detail_url="https://example.com/d/1")


def _add_image(doc: ArbitrationDocument, page_index: int, url: str | None = None) -> ArbitrationDocumentImage:
    # None = 未指定（补默认 URL）；显式传 "" 表示「无本地文件也无 URL」的坏数据
    source_url = url if url is not None else f"https://example.com/img/{page_index}.png"
    return ArbitrationDocumentImage.objects.create(document=doc, page_index=page_index, source_url=source_url)


@pytest.fixture(autouse=True)
def _stub_doxify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Doxify 依赖 ~/.workbuddy 外部脚本，打桩为直通，避免机器差异。"""
    monkeypatch.setattr(parsing_service, "clean_text", lambda t: (t, {}))
    monkeypatch.setattr(parsing_service, "clean_markdown", lambda m: (m, {}))


class TestParseSuccess:
    def test_multi_page_joined_in_page_order(self, doc: ArbitrationDocument, monkeypatch: pytest.MonkeyPatch) -> None:
        # 故意乱序插入，验证按 page_index 升序解析
        _add_image(doc, page_index=1)
        _add_image(doc, page_index=0)

        parser = MagicMock()
        parser.parse_document.side_effect = lambda file_path, file_type, **kw: MagicMock(
            text=f"text-of-{file_path}", markdown=f"md-of-{file_path}"
        )
        monkeypatch.setattr(parsing_service, "get_document_parser", lambda backend: parser)
        monkeypatch.setattr(parsing_service, "_fetch_image_to_temp", lambda url: f"/tmp/fake-{url[-5]}.png")

        result = parsing_service.parse_arbitration_document(doc, backend="mineru")

        assert result == {"success": True, "doc_id": doc.id, "pages": 2}
        doc.refresh_from_db()
        assert doc.parse_status == ParseStatus.DONE
        assert doc.parse_backend == "mineru"
        assert doc.parsed_text == "text-of-/tmp/fake-0.png\n\ntext-of-/tmp/fake-1.png"
        assert doc.parsed_markdown == "md-of-/tmp/fake-0.png\n\nmd-of-/tmp/fake-1.png"
        assert doc.parse_error == ""
        # 送 OCR 的顺序 = 页码顺序，扩展名取自 URL
        paths = [call.kwargs["file_path"] for call in parser.parse_document.call_args_list]
        assert paths == ["/tmp/fake-0.png", "/tmp/fake-1.png"]
        assert all(call.kwargs["file_type"] == "png" for call in parser.parse_document.call_args_list)

    def test_local_file_branch_uses_stored_path(
        self, doc: ArbitrationDocument, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.core.files.base import ContentFile

        img = _add_image(doc, page_index=0, url="")
        img.image.save("labor-arbitration-test/page.jpg", ContentFile(b"jpg-bytes"), save=True)

        parser = MagicMock()
        parser.parse_document.return_value = MagicMock(text="t", markdown="m")
        monkeypatch.setattr(parsing_service, "get_document_parser", lambda backend: parser)

        fetch_calls: list[str] = []

        def spy_fetch(url: str) -> str:
            fetch_calls.append(url)
            return "/tmp/never.png"

        monkeypatch.setattr(parsing_service, "_fetch_image_to_temp", spy_fetch)

        result = parsing_service.parse_arbitration_document(doc, backend="local")

        assert result["success"] is True
        assert fetch_calls == []  # 有本地文件时不下载
        assert parser.parse_document.call_args.kwargs["file_type"] == "jpg"

    def test_temp_download_cleaned_up(self, doc: ArbitrationDocument, monkeypatch: pytest.MonkeyPatch) -> None:
        _add_image(doc, page_index=0)

        def fake_fetch(url: str) -> str:
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            return path

        parser = MagicMock()
        parser.parse_document.return_value = MagicMock(text="t", markdown="m")
        monkeypatch.setattr(parsing_service, "get_document_parser", lambda backend: parser)
        monkeypatch.setattr(parsing_service, "_fetch_image_to_temp", fake_fetch)

        result = parsing_service.parse_arbitration_document(doc, backend="local")

        assert result["success"] is True
        # 解析用的临时文件在 finally 中被清理
        used_path = parser.parse_document.call_args.kwargs["file_path"]
        assert not os.path.exists(used_path)


class TestParseFailures:
    def test_no_images_marks_failed(self, doc: ArbitrationDocument, monkeypatch: pytest.MonkeyPatch) -> None:
        result = parsing_service.parse_arbitration_document(doc, backend="local")

        assert result["success"] is False
        assert "图片" in result["error"]
        doc.refresh_from_db()
        assert doc.parse_status == ParseStatus.FAILED
        assert "图片" in doc.parse_error

    def test_parser_exception_marks_failed(self, doc: ArbitrationDocument, monkeypatch: pytest.MonkeyPatch) -> None:
        _add_image(doc, page_index=0)
        parser = MagicMock()
        parser.parse_document.side_effect = RuntimeError("OCR 引擎爆炸")
        monkeypatch.setattr(parsing_service, "get_document_parser", lambda backend: parser)
        monkeypatch.setattr(parsing_service, "_fetch_image_to_temp", lambda url: "/tmp/fake.png")

        result = parsing_service.parse_arbitration_document(doc, backend="textin")

        assert result["success"] is False
        assert "OCR 引擎爆炸" in result["error"]
        doc.refresh_from_db()
        assert doc.parse_status == ParseStatus.FAILED
        assert doc.parse_backend == "textin"

    def test_image_without_file_or_url_skipped(self, doc: ArbitrationDocument, monkeypatch: pytest.MonkeyPatch) -> None:
        _add_image(doc, page_index=0, url="")
        _add_image(doc, page_index=1)

        parser = MagicMock()
        parser.parse_document.return_value = MagicMock(text="只有一页", markdown="m")
        monkeypatch.setattr(parsing_service, "get_document_parser", lambda backend: parser)
        monkeypatch.setattr(parsing_service, "_fetch_image_to_temp", lambda url: "/tmp/fake-1.png")

        result = parsing_service.parse_arbitration_document(doc, backend="local")

        assert result["success"] is True
        assert parser.parse_document.call_count == 1  # 无文件无 URL 的页被跳过


class TestStatusTransition:
    def test_processing_written_before_parse(self, doc: ArbitrationDocument, monkeypatch: pytest.MonkeyPatch) -> None:
        """进入解析时先落 PROCESSING，失败也保留该状态轨迹（FAILED 覆盖）。"""
        _add_image(doc, page_index=0)
        statuses: list[str] = []
        real_save = ArbitrationDocument.save

        def spy_save(self: ArbitrationDocument, *args: Any, **kwargs: Any) -> None:
            statuses.append(self.parse_status)
            real_save(self, *args, **kwargs)

        parser = MagicMock()
        parser.parse_document.return_value = MagicMock(text="t", markdown="m")
        monkeypatch.setattr(parsing_service, "get_document_parser", lambda backend: parser)
        monkeypatch.setattr(parsing_service, "_fetch_image_to_temp", lambda url: "/tmp/fake.png")
        monkeypatch.setattr(ArbitrationDocument, "save", spy_save)

        parsing_service.parse_arbitration_document(doc, backend="local")

        assert statuses[0] == ParseStatus.PROCESSING
        assert ParseStatus.DONE in statuses
        assert doc.crawl_status == DocumentCrawlStatus.PENDING  # 解析不动爬取状态
