"""材料包删除时回收「派生数据」的三条降级与容错路径。

存在理由：``delete_manual_message`` 除了删收件箱行与物理附件，还要顺手回收
pdf_splitting 侧的派生数据（任务行 / 任务目录 / OCR 缓存）。那部分**必须以"尽力
而为"运行**——此时材料包已经真的删掉了，若清理抛异常，用户会收到"删除失败"，
但重开列表会发现包已经不见了，是最容易引发反复操作的错误提示。

本文件锁三件事：

1. 追加附件时压缩包被全部过滤（空包）要报 ``ARCHIVE_EMPTY``，而不是静默成功
   ——否则用户以为加进去了；
2. 回收函数本身抛异常时，删除照常成功；
3. ``page_count`` 是脏值（"三页"）时降级成"按文件名清理"，不能整条跳过
   ——跳过就意味着下次上传同名文件会复用已删材料的分段结果。

测试数据全部虚构。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.message_hub.models import InboxMessage
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import (
    append_manual_attachments,
    create_manual_message,
    delete_manual_message,
    get_or_create_manual_source,
)

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4 derived-cleanup-fixture"


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """MEDIA_ROOT → 临时目录：``delete_media_file`` 会真的删盘上文件，不隔离就动真数据。"""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _cleanup(msg: InboxMessage) -> None:
    metas = msg.attachments_meta
    for att in metas if isinstance(metas, list) else []:
        if not isinstance(att, dict):
            continue
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    InboxMessage.objects.filter(pk=msg.pk).delete()


def _pack(*, name: str = "卷宗.pdf", page_count: Any = 3) -> InboxMessage:
    msg = create_manual_message([SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")])
    if page_count is not None:
        metas = list(msg.attachments_meta or [])
        metas[0]["page_count"] = page_count
        msg.attachments_meta = metas
        msg.save(update_fields=["attachments_meta"])
    return msg


def _empty_zip() -> SimpleUploadedFile:
    """只有目录条目、没有任何文件内容的 zip（展开后一个文件都没有）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("empty-folder/", "")
    return SimpleUploadedFile("空材料包.zip", buf.getvalue(), content_type="application/zip")


class TestAppendArchiveExpandsToNothing:
    def test_空压缩包报错而不是静默成功(self) -> None:
        """展开后一个文件都没有必须报 ARCHIVE_EMPTY。

        静默成功的话用户以为附件加进去了，实际材料包还是原来的内容——等到自动
        识别时才发 现"少了几份材料"，而那时已经过了很久。
        """
        msg = _pack(name="已有.pdf")
        try:
            with pytest.raises(ValidationException) as exc_info:
                append_manual_attachments(msg, [_empty_zip()])

            assert exc_info.value.code == "ARCHIVE_EMPTY"
            msg.refresh_from_db()
            assert len(msg.attachments_meta) == 1, "报错时不得留下半追加的元信息"
        finally:
            _cleanup(msg)


class TestPurgeDerivedDataResilience:
    def test_回收函数抛异常时删除仍然成功(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """清理是尽力而为：材料包已经删了，清理失败不该让用户看到"删除失败"。"""
        msg = _pack(name="清理失败.pdf")
        pk = msg.pk

        from apps.pdf_splitting.services import cleanup_service

        def boom(**_kwargs: Any) -> dict[str, int]:
            raise RuntimeError("cleanup down")

        monkeypatch.setattr(cleanup_service, "purge_split_jobs_for_attachment", boom)

        assert delete_manual_message(msg) == 1
        assert not InboxMessage.objects.filter(pk=pk).exists()

    def test_脏页数降级成按文件名清理(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``page_count`` 是 "三页" 这种脏值时，转 int 失败必须降级为 None。

        None 的语义是"只按文件名匹配"（宁可多留也不误删别的尺寸文件），
        而不是"跳过清理"——跳过等于下次上传同名文件复用已删材料的结果。
        """
        msg = _pack(name="脏页数.pdf", page_count="三页")
        pk = msg.pk
        calls: list[dict[str, Any]] = []

        from apps.pdf_splitting.services import cleanup_service

        def spy(**kwargs: Any) -> dict[str, int]:
            calls.append(kwargs)
            return {"jobs": 0, "dirs": 0, "ocr_cache": 0}

        monkeypatch.setattr(cleanup_service, "purge_split_jobs_for_attachment", spy)

        delete_manual_message(msg)

        assert calls == [{"source_name": "脏页数.pdf", "total_pages": None, "deleting_message_id": pk}]

    def test_页数为None时传None(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """附件元信息缺 ``page_count``（老数据）时同样走"只按文件名"口径。"""
        msg = _pack(name="无页数.pdf", page_count=None)
        calls: list[dict[str, Any]] = []

        from apps.pdf_splitting.services import cleanup_service

        monkeypatch.setattr(
            cleanup_service,
            "purge_split_jobs_for_attachment",
            lambda **kwargs: calls.append(kwargs) or {"jobs": 0, "dirs": 0, "ocr_cache": 0},
        )

        delete_manual_message(msg)

        assert calls[0]["total_pages"] is None
        assert calls[0]["source_name"] == "无页数.pdf"

    def test_清理服务导入失败时跳过而不崩(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pdf_splitting 侧模块导入炸掉（依赖缺失/循环导入）时，删材料包也要能走完。"""
        msg = _pack(name="导入失败.pdf")
        pk = msg.pk

        import builtins

        real_import = builtins.__import__

        def broken_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "apps.pdf_splitting.services.cleanup_service":
                raise ImportError("cleanup module unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", broken_import)

        assert delete_manual_message(msg) == 1
        assert not InboxMessage.objects.filter(pk=pk).exists()

    def test_没有附件时不调用清理服务(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """空材料包没什么可清理的；白调一次会真的去扫一遍 DB。"""
        msg = InboxMessage.objects.create(
            source=get_or_create_manual_source(),
            message_id="manual-no-attach-derive",
            subject="空材料包",
            received_at=timezone.now(),
            attachments_meta=[],
        )
        calls: list[dict[str, Any]] = []

        from apps.pdf_splitting.services import cleanup_service

        monkeypatch.setattr(cleanup_service, "purge_split_jobs_for_attachment", lambda **kwargs: calls.append(kwargs))

        delete_manual_message(msg)

        assert calls == []
