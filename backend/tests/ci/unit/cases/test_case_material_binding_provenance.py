"""归案 bind 链路透传预处理溯源的 DB 测试（django_db，由主会话集中跑）。

锁住：
1. bind 传 source_message_id/source_segment_ref → 落库 + 计算绑定附件 SHA-256；
2. 同一附件无溯源重复绑定 → 保留既有溯源（不清空 md 链接）；
3. replace_material_file 换文件 → 清哈希+段 ref（字节已变），保留包级来源。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.cases.models import CaseLogAttachment, CaseMaterial
from apps.cases.services.material.case_material_binding_workflow import CaseMaterialBindingWorkflow
from apps.cases.services.material.case_material_service import CaseMaterialService
from apps.testing.factories import CaseFactory, CaseLogFactory

_BYTES = b"%PDF-1.4 synthetic evidence bytes"
_HASH = hashlib.sha256(_BYTES).hexdigest()


def _attachment(case, name: str = "seg.pdf", data: bytes = _BYTES):
    log = CaseLogFactory(case=case)
    return CaseLogAttachment.objects.create(log=log, file=SimpleUploadedFile(name, data), original_filename=name)


def _bind_item(att_id: int, **extra):
    return {"attachment_id": att_id, "category": "party", "type_name": "借款合同", "side": "our", **extra}


@pytest.mark.django_db
class TestBindProvenance:
    def test_bind_stores_provenance_and_hash(self, case, tmp_path: Path) -> None:
        with override_settings(MEDIA_ROOT=tmp_path):
            att = _attachment(case)
            workflow = CaseMaterialBindingWorkflow(case_service=MagicMock())
            workflow.bind_materials(case.id, [_bind_item(att.id, source_message_id=11, source_segment_ref="s0")])
            m = CaseMaterial.objects.get(source_attachment=att)
        assert m.source_message_id == 11
        assert m.source_segment_ref == "s0"
        assert m.source_file_hash == _HASH

    def test_bind_without_provenance_leaves_fields_empty(self, case, tmp_path: Path) -> None:
        with override_settings(MEDIA_ROOT=tmp_path):
            att = _attachment(case)
            CaseMaterialBindingWorkflow(case_service=MagicMock()).bind_materials(case.id, [_bind_item(att.id)])
            m = CaseMaterial.objects.get(source_attachment=att)
        assert m.source_message_id is None
        assert m.source_segment_ref == ""
        assert m.source_file_hash == ""

    def test_rebind_without_provenance_preserves_existing(self, case, tmp_path: Path) -> None:
        with override_settings(MEDIA_ROOT=tmp_path):
            att = _attachment(case)
            workflow = CaseMaterialBindingWorkflow(case_service=MagicMock())
            workflow.bind_materials(case.id, [_bind_item(att.id, source_message_id=11, source_segment_ref="s0")])
            # 旧前端/手工绑定不带溯源 → 既有溯源不被清掉
            workflow.bind_materials(case.id, [_bind_item(att.id, type_name="借款合同（改）")])
            m = CaseMaterial.objects.get(source_attachment=att)
        assert m.source_message_id == 11
        assert m.source_segment_ref == "s0"
        assert m.source_file_hash == _HASH
        assert m.type_name == "借款合同（改）"


@pytest.mark.django_db
class TestReplaceClearsByteProvenance:
    def test_replace_clears_hash_and_ref_keeps_message(self, case, tmp_path: Path) -> None:
        with override_settings(MEDIA_ROOT=tmp_path):
            old = _attachment(case, "old.pdf")
            new = _attachment(case, "new.pdf", b"%PDF-1.4 different bytes")
            workflow = CaseMaterialBindingWorkflow(case_service=MagicMock())
            workflow.bind_materials(case.id, [_bind_item(old.id, source_message_id=11, source_segment_ref="s0")])
            m = CaseMaterial.objects.get(source_attachment=old)
            service = CaseMaterialService(case_service=MagicMock())
            service.replace_material_file(case.id, m.id, new.id)
            m.refresh_from_db()
        assert m.source_attachment_id == new.id
        assert m.source_file_hash == ""
        assert m.source_segment_ref == ""
        assert m.source_message_id == 11  # 包级来源仍成立
