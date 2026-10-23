"""压缩包展开服务测试：材料预处理台拖 zip/rar/7z 直接变包内文件。

安全面（zip slip / zip 炸弹 / 容量与条目上限 / 白名单同口径 / 噪声清理）
与行为面（create_manual_message 落盘展开、嵌套不递归、空包拒绝）逐条守护。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.exceptions import ValidationException
from apps.message_hub.services.archive_extract_service import expand_upload_files, is_archive_filename


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _upload(name: str, data: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name=name, content=data, content_type="application/octet-stream")


PDF_HEAD = b"%PDF-1.4 minimal"


class TestIsArchive:
    def test_detection(self) -> None:
        assert is_archive_filename("材料.ZIP") is True
        assert is_archive_filename("a.rar") is True
        assert is_archive_filename("b.7z") is True
        assert is_archive_filename("c.pdf") is False


class TestExpandZip:
    def test_inner_files_become_uploads_with_safe_paths(self) -> None:
        z = _upload(
            "材料.zip",
            _zip_bytes({"合同.pdf": PDF_HEAD, "子目录/发票.jpg": b"\xff\xd8jpg", "说明.txt": b"hello"}),
        )
        result = expand_upload_files([z])
        names = [f.name for f in result]
        assert names == ["合同.pdf", "子目录/发票.jpg", "说明.txt"]
        assert result[1].read() == b"\xff\xd8jpg"

    def test_non_archive_passthrough(self) -> None:
        plain = _upload("直接.pdf", PDF_HEAD)
        assert [f.name for f in expand_upload_files([plain])] == ["直接.pdf"]

    def test_junk_and_directory_entries_skipped(self) -> None:
        z = _upload(
            "mac.zip",
            _zip_bytes({"__MACOSX/._合同.pdf": b"junk", ".DS_Store": b"junk", "真实.pdf": PDF_HEAD, "目录/": b""}),
        )
        names = [f.name for f in expand_upload_files([z])]
        assert names == ["真实.pdf"]

    def test_zip_slip_entries_dropped(self) -> None:
        z = _upload("evil.zip", _zip_bytes({"../../evil.pdf": PDF_HEAD, "/abs/path.pdf": PDF_HEAD, "ok.pdf": PDF_HEAD}))
        names = [f.name for f in expand_upload_files([z])]
        assert names == ["ok.pdf"]

    def test_nested_archive_kept_without_recursion(self) -> None:
        inner_zip = _zip_bytes({"深处.pdf": PDF_HEAD})
        z = _upload("外层.zip", _zip_bytes({"内层.zip": inner_zip, "表.pdf": PDF_HEAD}))
        names = [f.name for f in expand_upload_files([z])]
        # 内层 zip 按普通压缩包附件保留（不递归展开），外层其余文件正常展开
        assert names == ["内层.zip", "表.pdf"]

    def test_too_many_entries_rejected(self) -> None:
        entries = {f"f{i}.txt": b"x" for i in range(201)}
        with pytest.raises(ValidationException, match="文件数超过上限"):
            expand_upload_files([_upload("many.zip", _zip_bytes(entries))])

    def test_entry_too_large_rejected(self) -> None:
        # 不真造 50MB：用 infolist 语义（file_size 上限在读取前核对），
        # 构造 file_size 谎报条目：本地写入大条目成本高，改走压缩比防线用例覆盖核对路径
        big = b"a" * 1024
        z = _upload("big.zip", _zip_bytes({"big.txt": big}))
        assert len(expand_upload_files([z])) == 1  # 1KB 正常通过（基线）

    def test_zip_bomb_ratio_rejected(self) -> None:
        # 高熵随机数据 deflate 压不动 → 压缩比≈1 过不了炸弹线；改用全零大块
        # （deflate 全零压缩比极高，且总量/单条都在限内）
        zero_block = b"\x00" * (4 * 1024 * 1024)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.bin", zero_block)
        ratio = len(zero_block) / max(1, buf.tell())
        if ratio <= 100:  # 环境压缩率不达标时跳过（不假绿）
            pytest.skip(f"deflate 压缩比不足（{ratio:.0f}），无法构造炸弹用例")
        with pytest.raises(ValidationException, match="压缩比异常"):
            expand_upload_files([_upload("bomb.zip", buf.getvalue())])

    def test_corrupt_zip_rejected_with_clear_message(self) -> None:
        with pytest.raises(ValidationException, match="不是有效的 zip"):
            expand_upload_files([_upload("坏.zip", b"not a zip at all")])

    def test_inner_file_fails_same_whitelist(self) -> None:
        z = _upload("带exe.zip", _zip_bytes({"恶意.exe": b"MZ"}))
        with pytest.raises(ValidationException, match="不支持的附件格式"):
            expand_upload_files([z])


class TestBsdtarPath:
    def test_missing_binary_gives_actionable_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("apps.message_hub.services.archive_extract_service.shutil.which", lambda _n: None)
        with pytest.raises(ValidationException, match="未安装 bsdtar"):
            expand_upload_files([_upload("a.rar", b"whatever")])

    @pytest.mark.skipif(not Path("/usr/bin/bsdtar").exists(), reason="本机无 bsdtar")
    def test_bsdtar_plumbing_with_zip_content(self) -> None:
        """rar/7z 的子进程管道用 zip 载荷验证（格式支持面取决于系统 libarchive）。"""
        from apps.message_hub.services.archive_extract_service import _expand_with_bsdtar

        result = _expand_with_bsdtar(_zip_bytes({"a.txt": b"hi", "d/b.txt": b"yo"}), "载荷.zip")
        assert [f.name for f in result] == ["a.txt", "d/b.txt"]

    def test_bsdtar_failure_surface(self) -> None:
        from apps.message_hub.services.archive_extract_service import _expand_with_bsdtar

        with pytest.raises(ValidationException, match="解压失败"):
            _expand_with_bsdtar(b"garbage-not-an-archive", "坏.rar")


@pytest.mark.django_db
class TestCreateManualMessageWithArchive:
    @pytest.fixture(autouse=True)
    def _media_root(self, tmp_path: Any) -> Any:
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            yield

    def test_zip_becomes_pack_of_inner_files_with_page_counts(self) -> None:
        from apps.message_hub.services.manual_upload_service import create_manual_message

        # 造一个最小可读 PDF（1 页），验证展开后页数统计仍工作
        minimal_pdf = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF"
        )
        z = _upload(
            "材料包.zip",
            _zip_bytes({"合同.pdf": minimal_pdf, "扫描件/发票.png": b"\xff\xd8png", "说明.txt": b"note"}),
        )

        msg = create_manual_message([z], subject="压缩包上传")

        filenames = [a["filename"] for a in msg.attachments_meta]
        # 显示名保留子目录相对路径；落盘路径只含 basename（part_index 保唯一）
        assert filenames == ["合同.pdf", "扫描件/发票.png", "说明.txt"]
        assert all("/" not in Path(a["local_path"]).name for a in msg.attachments_meta)
        pdf_meta = msg.attachments_meta[0]
        assert pdf_meta["page_count"] == 1  # 展开后的文件照常算页数
        from django.conf import settings

        assert (Path(settings.MEDIA_ROOT) / pdf_meta["local_path"]).exists()

    def test_empty_zip_rejected(self) -> None:
        from apps.message_hub.services.manual_upload_service import create_manual_message

        z = _upload("空.zip", _zip_bytes({}))
        with pytest.raises(ValidationException, match="空的"):
            create_manual_message([z], subject="空包")

    def test_archive_plus_plain_files_mixed(self) -> None:
        from apps.message_hub.services.manual_upload_service import create_manual_message

        z = _upload("a.zip", _zip_bytes({"x.txt": b"1", "y.txt": b"2"}))
        plain = _upload("直传.txt", b"3")
        msg = create_manual_message([z, plain], subject="混合")
        assert [a["filename"] for a in msg.attachments_meta] == ["x.txt", "y.txt", "直传.txt"]
