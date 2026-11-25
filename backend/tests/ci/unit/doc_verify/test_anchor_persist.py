"""基线落库的单测：幂等、只增不改、字段完整。

为什么这三件事要单独测：基线是「我们实际发出去的那一份」的唯一证据。
- 幂等错了 → 同一份纸重复出站留下多条基线，核对时会拿错版本；
- 「只增不改」破了 → 基线被后一次捕获静默覆盖，等于销毁证据；
- 字段漏映射 → 核对侧拿到空指纹 / 空正文，报告会说「未发现差异」而实际没比。

样本字节全部现场合成，测试库必须是 ``DB_NAME=test_fachuan_dev``。
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import pymupdf
import pytest

from apps.cases.models import Case
from apps.doc_verify.models.artifact import CaptureSource, OutboundArtifact
from apps.doc_verify.services.anchor.area_mask import default_masks
from apps.doc_verify.services.anchor.capture import capture_baseline
from apps.doc_verify.services.anchor.persist import create_artifact

pytestmark = pytest.mark.django_db


def _make_digital_pdf(page_texts: Sequence[str]) -> bytes:
    document = pymupdf.open()
    for index, body in enumerate(page_texts, start=1):
        page = document.new_page()
        page.insert_text((72, 100), f"page {index}: {body}", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _capture(data: bytes, doc_type: str = "起诉状", version: str = "V1") -> Any:
    return capture_baseline(
        data=data,
        file_name=f"{doc_type}.pdf",
        doc_type=doc_type,
        version=version,
        masks=default_masks(doc_type),
    )


class TestCreateArtifact:
    def test_same_bytes_twice_keep_one_row(self) -> None:
        case = Case.objects.create(name="基线幂等案")
        data = _make_digital_pdf(["alpha body", "beta body"])

        first = create_artifact(case=case, baseline=_capture(data))
        second = create_artifact(case=case, baseline=_capture(data))

        assert first.pk == second.pk
        assert OutboundArtifact.objects.filter(case=case).count() == 1

    def test_one_character_change_creates_second_row(self) -> None:
        case = Case.objects.create(name="基线改字案")
        original = _make_digital_pdf(["alpha body"])
        edited = _make_digital_pdf(["alpha bodY"])

        first = create_artifact(case=case, baseline=_capture(original))
        second = create_artifact(case=case, baseline=_capture(edited))

        assert first.pk != second.pk
        assert first.file_sha256 != second.file_sha256
        assert OutboundArtifact.objects.filter(case=case).count() == 2

    def test_existing_row_is_never_overwritten(self) -> None:
        case = Case.objects.create(name="基线只增不改案")
        data = _make_digital_pdf(["alpha body"])
        original = create_artifact(case=case, baseline=_capture(data), note="出站时捕获")

        reused = create_artifact(
            case=case,
            baseline=_capture(data),
            capture_source=CaptureSource.SEND_TO_CLIENT,
            verify_required=True,
            note="试图覆盖",
            policy_snapshot={"min_tier": 2},
        )

        assert reused.pk == original.pk
        stored = OutboundArtifact.objects.get(pk=original.pk)
        assert stored.note == "出站时捕获"
        assert stored.capture_source == CaptureSource.MANUAL
        assert stored.verify_required is False
        assert stored.policy_snapshot == {}

    def test_fields_are_mapped_from_baseline(self) -> None:
        case = Case.objects.create(name="基线字段案")
        data = _make_digital_pdf(["alpha body", "beta body", "gamma body"])
        baseline = _capture(data, doc_type="送达地址确认书", version="V2_20261125")

        artifact = create_artifact(
            case=case,
            baseline=baseline,
            capture_source=CaptureSource.EXPORT,
            verify_required=True,
            policy_snapshot={"min_tier": 1},
            note="导出定稿时捕获",
        )

        assert artifact.doc_type == "送达地址确认书"
        assert artifact.version == "V2_20261125"
        assert artifact.file_sha256 == hashlib.sha256(data).hexdigest()
        assert artifact.page_count == 3
        assert [list(signature) for signature in baseline.page_signatures] == artifact.page_signatures
        assert artifact.text_layer == baseline.text
        assert artifact.masks == [{"kind": "signature_zone", "doc_type": "送达地址确认书", "tail_lines": 3}]
        assert artifact.capture_source == CaptureSource.EXPORT
        assert artifact.verify_required is True
        assert artifact.policy_snapshot == {"min_tier": 1}
        assert artifact.note == "导出定稿时捕获"
        assert artifact.captured_by is None

    def test_same_bytes_under_other_version_creates_second_row(self) -> None:
        """同一份字节也可能在两个版本标签下出站过，版本是幂等键的一部分。"""
        case = Case.objects.create(name="基线版本案")
        data = _make_digital_pdf(["alpha body"])

        first = create_artifact(case=case, baseline=_capture(data, version="V1"))
        second = create_artifact(case=case, baseline=_capture(data, version="V2"))

        assert first.pk != second.pk
        assert OutboundArtifact.objects.filter(case=case).count() == 2

    def test_artifact_without_case_is_allowed(self) -> None:
        """人工补锚可以没有案件（模型允许 case 为空）。"""
        data = _make_digital_pdf(["alpha body"])

        artifact = create_artifact(case=None, baseline=_capture(data))
        again = create_artifact(case=None, baseline=_capture(data))

        assert artifact.case is None
        assert again.pk == artifact.pk
        assert OutboundArtifact.objects.filter(case__isnull=True).count() == 1
