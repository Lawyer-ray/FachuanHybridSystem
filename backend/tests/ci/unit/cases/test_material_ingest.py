"""材料归案：目录 → 附件 + 案件材料 + 解析任务，且重复执行不重复登记。

真机（案卷 489）暴露的断点是「材料在律师本地文件夹里、库里 materials=[]」，
于是 assess 只能回答「材料一项都没有」。这个服务就是把那一步补上。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apps.cases.models import Case
from apps.cases.models.log import CaseLog
from apps.cases.models.material import CaseMaterial
from apps.cases.services.material import material_ingest_service
from apps.document_parsing.models import DocumentParsingTask
from apps.organization.models import Lawyer

pytestmark = pytest.mark.django_db


def _case(name: str = "材料归案测试案") -> Case:
    return Case.objects.create(name=name, yz_wid="")


@pytest.fixture()
def actor() -> Lawyer:
    """归案日志需要署名：`CaseLog.actor` 是 PROTECT，测试里给一个真律师。"""
    return Lawyer.objects.create(username="test-lawyer", real_name="测试律师", license_no="TEST-001")


def _stub_parse(monkeypatch: pytest.MonkeyPatch, *, text: str = "合同正文：承包金 384277 元") -> None:
    """把解析换成假实现：本用例测编排（登记/幂等/绑定），不测 OCR。"""

    class _Service:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def parse_document(self, **_kwargs: Any) -> Any:
            # 用 SimpleNamespace 而不是在类体里 `text = text`：类体不闭包外层函数的同名变量
            return SimpleNamespace(text=text, markdown="", parse_method="stub", metadata={})

    monkeypatch.setattr("apps.document_parsing.services.document_parser.DocumentParserService", _Service)


def test_ingest_creates_attachment_material_and_parsing_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actor: Lawyer
) -> None:
    _stub_parse(monkeypatch)
    case = _case()
    (tmp_path / "合同.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    (tmp_path / "视频.mp4").write_bytes(b"junk")

    created = material_ingest_service.ingest_directory(case_id=case.pk, directory=tmp_path, actor=actor)

    assert len(created) == 1  # 只有 pdf 被归案
    material = created[0]
    assert material.source_attachment.original_filename == "合同.pdf"
    assert material.parsing_task is not None
    assert material.parsing_task.status == DocumentParsingTask.Status.COMPLETED
    assert "384277" in (material.parsing_task.text or "")
    assert CaseLog.objects.filter(case=case).count() == 1


def test_ingest_is_idempotent_by_content_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actor: Lawyer) -> None:
    _stub_parse(monkeypatch)
    case = _case()
    (tmp_path / "合同.pdf").write_bytes(b"%PDF-1.4 same bytes")

    first = material_ingest_service.ingest_directory(case_id=case.pk, directory=tmp_path, actor=actor)
    second = material_ingest_service.ingest_directory(case_id=case.pk, directory=tmp_path, actor=actor)

    assert len(first) == 1
    assert second == []
    assert CaseMaterial.objects.filter(case=case).count() == 1


def test_parse_failure_keeps_material_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actor: Lawyer
) -> None:
    """解析挂了也要把材料留在库里：文件已上传，回滚比「没正文」更难解释。"""

    class _Boom:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def parse_document(self, **_kwargs: Any) -> Any:
            raise RuntimeError("OCR 全挂")

    monkeypatch.setattr("apps.document_parsing.services.document_parser.DocumentParserService", _Boom)
    case = _case()
    (tmp_path / "扫描件.pdf").write_bytes(b"%PDF-1.4 unreadable")

    created = material_ingest_service.ingest_directory(case_id=case.pk, directory=tmp_path, actor=actor)

    assert len(created) == 1
    assert created[0].parsing_task is None


def test_empty_and_oversized_files_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actor: Lawyer) -> None:
    _stub_parse(monkeypatch)
    case = _case()
    (tmp_path / "空文件.pdf").write_bytes(b"")
    big = tmp_path / "超大.pdf"
    big.write_bytes(b"x" * (material_ingest_service.MAX_FILE_BYTES + 1))

    created = material_ingest_service.ingest_directory(case_id=case.pk, directory=tmp_path, actor=actor)

    assert created == []
