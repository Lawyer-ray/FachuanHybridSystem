from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.doc_convert.constants import MbidDefinition, get_mbid_by_category, get_mbid_set
from apps.doc_convert.exceptions import (
    FileTooLargeError,
    InvalidFileTypeError,
    InvalidMbidError,
    ZnszjInvalidResponseError,
    ZnszjUnavailableError,
)
from apps.doc_convert.services.doc_convert_service import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    DocConvertService,
)


class TestDocConvertServiceGetMbidList:
    def test_returns_grouped_dict(self):
        svc = DocConvertService(znszj_client=MagicMock())
        result = svc.get_mbid_list()
        assert isinstance(result, dict)
        assert len(result) > 0
        for cat, items in result.items():
            assert isinstance(cat, str)
            assert isinstance(items, list)
            for item in items:
                assert "mbid" in item
                assert "name" in item


def _valid_docx_bytes(padding: int = 0) -> bytes:
    """构造一个**内容合法**的最小 docx（zip 里带 word/document.xml）。

    ═══ 为什么测试数据要真 ═══
    本文件早先用 `b"data"` 当文件内容 —— 那时 service 只看扩展名，能过。
    后来补了内容校验（因为坏文件会被归成 502「服务挂了」，见
    doc_convert_service._assert_parsable 的说明），`b"data"` 就成了
    「扩展名对但内容是坏的」，被正确地拒掉了。
    测试数据应当反映真实输入：真实场景里上传的 docx 是真的 zip。
    """
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        doc = "<w:document/>" + (" " * max(0, padding - 512))
        zf.writestr("word/document.xml", doc)
        zf.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


def _valid_doc_bytes() -> bytes:
    """OLE2 复合文档头（老 .doc）。校验层只认魔数，剩下交给 znszj。"""
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64


def _valid_pdf_bytes() -> bytes:
    """最小可用 PDF（校验层看 %PDF 头）。"""
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class TestDocConvertServiceConvertDocument:
    def test_invalid_extension_raises(self):
        svc = DocConvertService(znszj_client=MagicMock())
        with pytest.raises(InvalidFileTypeError):
            svc.convert_document(file_content=b"data", filename="test.txt", mbid="mjjdqsz")

    def test_invalid_mbid_raises(self):
        svc = DocConvertService(znszj_client=MagicMock())
        with pytest.raises(InvalidMbidError):
            svc.convert_document(file_content=_valid_docx_bytes(), filename="test.docx", mbid="INVALID_MBID")

    def test_file_too_large_raises(self):
        svc = DocConvertService(znszj_client=MagicMock())
        large_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(FileTooLargeError):
            svc.convert_document(file_content=large_content, filename="big.docx", mbid="mjjdqsz")

    def test_success_docx(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"converted"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=_valid_docx_bytes(), filename="test.docx", mbid="mjjdqsz")
        assert result == b"converted"
        mock_client.convert_document.assert_called_once_with(file_content=_valid_docx_bytes(), filename="test.docx", mbid="mjjdqsz")

    def test_success_doc(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"ok"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=_valid_doc_bytes(), filename="test.doc", mbid="lhjfqsz")
        assert result == b"ok"

    def test_success_pdf(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"pdf_result"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=_valid_pdf_bytes(), filename="test.pdf", mbid="mmhtqsz")
        assert result == b"pdf_result"

    def test_znszj_unavailable_error_reraised(self):
        mock_client = MagicMock()
        mock_client.convert_document.side_effect = ZnszjUnavailableError(detail="down")
        svc = DocConvertService(znszj_client=mock_client)
        with pytest.raises(ZnszjUnavailableError):
            svc.convert_document(file_content=_valid_docx_bytes(), filename="test.docx", mbid="mjjdqsz")

    def test_znszj_invalid_response_reraised(self):
        mock_client = MagicMock()
        mock_client.convert_document.side_effect = ZnszjInvalidResponseError(detail="bad format")
        svc = DocConvertService(znszj_client=mock_client)
        with pytest.raises(ZnszjInvalidResponseError):
            svc.convert_document(file_content=_valid_docx_bytes(), filename="test.docx", mbid="mjjdqsz")

    def test_generic_exception_wrapped(self):
        mock_client = MagicMock()
        mock_client.convert_document.side_effect = RuntimeError("unexpected")
        svc = DocConvertService(znszj_client=mock_client)
        with pytest.raises(ZnszjUnavailableError):
            svc.convert_document(file_content=_valid_docx_bytes(), filename="test.docx", mbid="mjjdqsz")

    def test_max_file_size_exactly_at_limit(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"ok"
        svc = DocConvertService(znszj_client=mock_client)
        # 撑到上限的字节里必须是**合法 docx**：内容校验在大小校验之后、调 znszj 之前，
        # 拿全 'x' 会被判成损坏文件（那是正确行为，只是测不到「刚好等于上限可过」）。
        #
        # ⚠️ 不能靠在合法 docx 后面追加字节来撑大 —— ZIP 的中央目录在文件尾部，
        # 追加数据会让 zipfile 报「不是 zip」（我第一版就这么写的）。
        # 正确做法是写 entry 时就用大内容，让 ZIP 结构本身完整。
        content = _valid_docx_bytes(padding=MAX_FILE_SIZE_BYTES)
        result = svc.convert_document(file_content=content, filename="test.docx", mbid="mjjdqsz")
        assert result == b"ok"

    def test_case_insensitive_extension(self):
        mock_client = MagicMock()
        mock_client.convert_document.return_value = b"ok"
        svc = DocConvertService(znszj_client=mock_client)
        result = svc.convert_document(file_content=_valid_docx_bytes(), filename="test.DOCX", mbid="mjjdqsz")
        assert result == b"ok"


class TestConstants:
    def test_allowed_extensions(self):
        assert ".docx" in ALLOWED_EXTENSIONS
        assert ".doc" in ALLOWED_EXTENSIONS
        assert ".pdf" in ALLOWED_EXTENSIONS

    def test_max_file_size(self):
        assert MAX_FILE_SIZE_MB == 20
        assert MAX_FILE_SIZE_BYTES == 20 * 1024 * 1024
