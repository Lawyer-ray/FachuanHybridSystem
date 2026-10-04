"""DocxExportService 单元测试。

覆盖 export_docx/_build_docx_bytes 全流程（真实 python-docx 渲染）、
空截图与插图失败的 ValidationException 分支、进度回调、标题/备注段落、
页码页眉 setup。截图图片用 PIL 生成、经 tmp_path MEDIA_ROOT 落盘。
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.chat_records.models import ChatRecordProject, ChatRecordScreenshot
from apps.chat_records.services.export.docx_export_service import DocxExportService
from apps.chat_records.services.export.export_types import ExportLayout
from apps.core.exceptions import ValidationException


def _png_bytes(color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 96), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def project(db: None) -> ChatRecordProject:
    return ChatRecordProject.objects.create(name="DOCX 导出测试项目")


def _make_screenshot(
    project: ChatRecordProject, *, title: str = "", note: str = "", content: bytes | None = None
) -> ChatRecordScreenshot:
    image = SimpleUploadedFile("shot.png", content or _png_bytes(), content_type="image/png")
    return ChatRecordScreenshot.objects.create(project=project, image=image, title=title, note=note)


class TestExportDocx:
    @pytest.mark.django_db
    def test_empty_screenshots_raises_validation(self, project) -> None:
        with pytest.raises(ValidationException, match="没有截图"):
            DocxExportService().export_docx(
                project=project,
                screenshots=[],
                layout=ExportLayout(images_per_page=2, show_page_number=True, header_text=""),
                filename="a.docx",
            )

    @pytest.mark.django_db
    def test_export_returns_contentfile_with_bytes(self, project, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        shots = [_make_screenshot(project, title="图1标题", note="图1备注") for _ in range(3)]

        result = DocxExportService().export_docx(
            project=project,
            screenshots=shots,
            layout=ExportLayout(images_per_page=2, show_page_number=False, header_text=""),
            filename="export.docx",
        )

        assert result.name == "export.docx"
        payload = result.read()
        assert payload[:2] == b"PK"  # docx 是 zip 容器
        assert len(payload) > 500

    @pytest.mark.django_db
    def test_progress_callback_called_per_image(self, project, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        shots = [_make_screenshot(project) for _ in range(3)]

        calls: list[tuple[int, int, str]] = []
        DocxExportService().export_docx(
            project=project,
            screenshots=shots,
            layout=ExportLayout(images_per_page=1, show_page_number=False, header_text=""),
            filename="progress.docx",
            progress_callback=lambda done, total, msg: calls.append((done, total, msg)),
        )

        assert [c[0] for c in calls] == [1, 2, 3]
        assert all(c[1] == 3 and c[2] == "生成中" for c in calls)

    @pytest.mark.django_db
    def test_corrupt_image_raises_insert_failure(self, project, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        # 非图片字节：PIL 打开失败 → ValidationException("Word 导出插图失败")
        shot = _make_screenshot(project, content=b"this is not an image")

        with pytest.raises(ValidationException, match="Word 导出插图失败"):
            DocxExportService().export_docx(
                project=project,
                screenshots=[shot],
                layout=ExportLayout(images_per_page=2, show_page_number=False, header_text=""),
                filename="bad.docx",
            )

    @pytest.mark.django_db
    def test_title_and_note_rendered_as_paragraphs(self, project, settings, tmp_path) -> None:
        """标题/备注写入单元格段落：解包 docx 校验文本存在。"""
        import zipfile

        settings.MEDIA_ROOT = tmp_path
        shot = _make_screenshot(project, title="标题X", note="备注Y")

        result = DocxExportService().export_docx(
            project=project,
            screenshots=[shot],
            layout=ExportLayout(images_per_page=2, show_page_number=False, header_text=""),
            filename="t.docx",
        )
        with zipfile.ZipFile(io.BytesIO(result.read())) as zf:
            document_xml = zf.read("word/document.xml").decode("utf-8")
        assert "标题X" in document_xml
        assert "备注Y" in document_xml

    @pytest.mark.django_db
    def test_header_text_and_page_number_setup(self, project, settings, tmp_path) -> None:
        """页眉文本 + 页码字段的 setup 分支不炸且进入产物。"""
        import zipfile

        settings.MEDIA_ROOT = tmp_path
        shot = _make_screenshot(project)

        result = DocxExportService().export_docx(
            project=project,
            screenshots=[shot],
            layout=ExportLayout(images_per_page=2, show_page_number=True, header_text="聊天记录导出"),
            filename="h.docx",
        )
        with zipfile.ZipFile(io.BytesIO(result.read())) as zf:
            names = zf.namelist()
            document_xml = zf.read("word/document.xml").decode("utf-8")
        assert "word/footer1.xml" in names or any(n.startswith("word/footer") for n in names)
        assert "聊天记录导出" in document_xml

    @pytest.mark.django_db
    def test_single_per_page_adds_page_breaks(self, project, settings, tmp_path) -> None:
        """每页 1 图时，多页之间插入分页符。"""
        import zipfile

        settings.MEDIA_ROOT = tmp_path
        shots = [_make_screenshot(project) for _ in range(2)]

        result = DocxExportService().export_docx(
            project=project,
            screenshots=shots,
            layout=ExportLayout(images_per_page=1, show_page_number=False, header_text=""),
            filename="p.docx",
        )
        with zipfile.ZipFile(io.BytesIO(result.read())) as zf:
            document_xml = zf.read("word/document.xml").decode("utf-8")
        assert 'w:type="page"' in document_xml

    @pytest.mark.django_db
    def test_multi_batch_without_trailing_break(self, project, settings, tmp_path) -> None:
        """最后一批之后不再补分页符：2 张图 2/页 只有一批，无分页符。"""
        import zipfile

        settings.MEDIA_ROOT = tmp_path
        shots = [_make_screenshot(project) for _ in range(2)]

        result = DocxExportService().export_docx(
            project=project,
            screenshots=shots,
            layout=ExportLayout(images_per_page=2, show_page_number=False, header_text=""),
            filename="np.docx",
        )
        with zipfile.ZipFile(io.BytesIO(result.read())) as zf:
            document_xml = zf.read("word/document.xml").decode("utf-8")
        assert 'w:type="page"' not in document_xml

    @pytest.mark.django_db
    def test_odd_batch_fills_partial_row(self, project, settings, tmp_path) -> None:
        """3 张图 2/页：第二批只有 1 张，仍正常导出。"""
        settings.MEDIA_ROOT = tmp_path
        shots = [_make_screenshot(project) for _ in range(3)]

        result = DocxExportService().export_docx(
            project=project,
            screenshots=shots,
            layout=ExportLayout(images_per_page=2, show_page_number=False, header_text=""),
            filename="odd.docx",
        )
        assert result.read()[:2] == b"PK"
