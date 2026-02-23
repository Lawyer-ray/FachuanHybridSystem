"""
外部模板智能填充 — 单元测试 + 属性测试

Feature: external-template-filling
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from apps.documents.models import (
    ExternalTemplate,
    ExternalTemplateFieldMapping,
    FillType,
    SourceType,
    TemplateCategory,
    TemplateStatus,
)
from apps.documents.models.fill_record import BatchFillTask, FillRecord
from apps.documents.services.external_template.fingerprint_service import (
    FingerprintService,
)

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_law_firm(**kwargs: Any) -> Any:
    """创建测试用律所。"""
    from apps.organization.models.law_firm import LawFirm

    defaults: dict[str, Any] = {"name": "测试律所"}
    defaults.update(kwargs)
    return LawFirm.objects.create(**defaults)


def _make_lawyer(law_firm: Any, **kwargs: Any) -> Any:
    """创建测试用律师。"""
    from apps.organization.models.lawyer import Lawyer

    import uuid

    username = kwargs.pop("username", f"lawyer_{uuid.uuid4().hex[:8]}")
    defaults: dict[str, Any] = {
        "username": username,
        "law_firm": law_firm,
    }
    defaults.update(kwargs)
    return Lawyer.objects.create(**defaults)


def _make_court(parent: Any = None, **kwargs: Any) -> Any:
    """创建测试用法院。"""
    from apps.core.models.court import Court

    import uuid

    defaults: dict[str, Any] = {
        "code": f"court_{uuid.uuid4().hex[:8]}",
        "name": f"测试法院_{uuid.uuid4().hex[:6]}",
        "level": 1,
        "is_active": True,
    }
    if parent is not None:
        defaults["parent"] = parent
    defaults.update(kwargs)
    return Court.objects.create(**defaults)


def _make_case(**kwargs: Any) -> Any:
    """创建测试用案件。"""
    from apps.cases.models import Case

    defaults: dict[str, Any] = {"name": "测试案件"}
    defaults.update(kwargs)
    return Case.objects.create(**defaults)


def _make_client(**kwargs: Any) -> Any:
    """创建测试用当事人(Client)。"""
    from apps.client.models.client import Client

    import uuid

    defaults: dict[str, Any] = {
        "name": f"当事人_{uuid.uuid4().hex[:6]}",
        "client_type": "natural",
    }
    defaults.update(kwargs)
    return Client.objects.create(**defaults)


def _make_case_party(case: Any, **kwargs: Any) -> Any:
    """创建测试用案件当事人。"""
    from apps.cases.models.party import CaseParty

    client = kwargs.pop("client", None) or _make_client()
    defaults: dict[str, Any] = {
        "case": case,
        "client": client,
    }
    defaults.update(kwargs)
    return CaseParty.objects.create(**defaults)


def _make_template(law_firm: Any, **kwargs: Any) -> ExternalTemplate:
    """创建测试用外部模板。"""
    defaults: dict[str, Any] = {
        "name": "测试模板",
        "category": TemplateCategory.PROPERTY_DECLARATION,
        "source_type": SourceType.COURT,
        "file_path": "documents/external_templates/1/test.docx",
        "original_filename": "test.docx",
        "file_size": 1024,
        "law_firm": law_firm,
    }
    defaults.update(kwargs)
    return ExternalTemplate.objects.create(**defaults)


def _make_mapping(template: ExternalTemplate, **kwargs: Any) -> ExternalTemplateFieldMapping:
    """创建测试用字段映射。"""
    defaults: dict[str, Any] = {
        "template": template,
        "position_locator": {"type": "paragraph", "paragraph_index": 0},
        "semantic_label": "测试字段",
        "placeholder_key": "case_name",
        "fill_type": FillType.TEXT,
    }
    defaults.update(kwargs)
    return ExternalTemplateFieldMapping.objects.create(**defaults)


def _create_test_docx(tmp_dir: Path, text_content: str = "测试内容") -> Path:
    """创建一个最小的测试 .docx 文件。"""
    docx_path = tmp_dir / "test.docx"
    # .docx 是 ZIP 格式，包含 word/document.xml
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>" + text_content + "</w:t></w:r></w:p>"
        "</w:body>"
        "</w:document>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(str(docx_path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/document.xml", document_xml)
    return docx_path


# ===========================================================================
# Task 16.1: 单元测试
# ===========================================================================


class TestEnumValues(TestCase):
    """单元测试: 枚举值数量和模型 Meta 配置"""

    def test_template_category_has_8_values(self) -> None:
        values = [c.value for c in TemplateCategory]
        assert len(values) == 8
        expected = {
            "property_declaration", "service_address", "creditor_declaration",
            "element_complaint", "power_of_attorney", "legal_aid",
            "preservation_application", "other",
        }
        assert set(values) == expected

    def test_source_type_has_5_values(self) -> None:
        values = [c.value for c in SourceType]
        assert len(values) == 5
        expected = {"court", "administrator", "arbitration", "administrative", "other"}
        assert set(values) == expected

    def test_fill_type_has_3_values(self) -> None:
        values = [c.value for c in FillType]
        assert len(values) == 3
        expected = {"text", "checkbox", "delete_inapplicable"}
        assert set(values) == expected

    def test_template_status_has_5_values(self) -> None:
        values = [c.value for c in TemplateStatus]
        assert len(values) == 5
        expected = {"uploaded", "analyzing", "analysis_failed", "mapped", "confirmed"}
        assert set(values) == expected

    def test_external_template_verbose_name(self) -> None:
        assert str(ExternalTemplate._meta.verbose_name) == "外部模板"

    def test_field_mapping_indexes_configured(self) -> None:
        index_fields = [
            tuple(idx.fields) for idx in ExternalTemplateFieldMapping._meta.indexes
        ]
        assert ("template", "sort_order") in index_fields


# ===========================================================================
# Task 16.2: Property 1 — ExternalTemplate 字段 Round-Trip
# **Validates: Requirements 1.1, 1.3, 13.1**
# ===========================================================================


class TestProperty1FieldRoundTrip(HypothesisTestCase):
    """
    Property 1: 使用随机合法字段值创建 ExternalTemplate 后从数据库重新查询，
    所有字段值应与写入值完全一致。

    **Validates: Requirements 1.1, 1.3, 13.1**
    """

    @given(
        name=st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != ""),
        category=st.sampled_from([c.value for c in TemplateCategory]),
        source_type=st.sampled_from([c.value for c in SourceType]),
        organization_name=st.text(max_size=100),
        file_size=st.integers(min_value=1, max_value=20 * 1024 * 1024),
        version=st.integers(min_value=1, max_value=999),
        is_active=st.booleans(),
        status=st.sampled_from([s.value for s in TemplateStatus]),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_field_values_roundtrip(
        self,
        name: str,
        category: str,
        source_type: str,
        organization_name: str,
        file_size: int,
        version: int,
        is_active: bool,
        status: str,
    ) -> None:
        law_firm = _make_law_firm()
        court = _make_court() if source_type == SourceType.COURT else None

        template = ExternalTemplate.objects.create(
            name=name,
            category=category,
            source_type=source_type,
            court=court,
            organization_name=organization_name,
            file_path="documents/external_templates/1/test.docx",
            original_filename="test.docx",
            file_size=file_size,
            version=version,
            is_active=is_active,
            status=status,
            law_firm=law_firm,
        )

        fetched = ExternalTemplate.objects.get(pk=template.pk)
        assert fetched.name == name
        assert fetched.category == category
        assert fetched.source_type == source_type
        assert fetched.organization_name == organization_name
        assert fetched.file_size == file_size
        assert fetched.version == version
        assert fetched.is_active == is_active
        assert fetched.status == status
        assert fetched.law_firm_id == law_firm.pk
        if court is not None:
            assert fetched.court_id == court.pk


# ===========================================================================
# Task 16.3: Property 2 — 版本号自增
# **Validates: Requirements 9.1, 9.2**
# ===========================================================================


class TestProperty2VersionAutoIncrement(HypothesisTestCase):
    """
    Property 2: 同一法院+类别组合上传新模板时，版本号应自增，
    旧版本 is_active 应为 False。

    **Validates: Requirements 9.1, 9.2**
    """

    @given(
        n_uploads=st.integers(min_value=2, max_value=5),
        category=st.sampled_from([c.value for c in TemplateCategory]),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_version_increments_and_old_deactivated(
        self,
        n_uploads: int,
        category: str,
    ) -> None:
        from apps.documents.services.external_template.analysis_service import (
            AnalysisService,
        )

        law_firm = _make_law_firm()
        court = _make_court()

        # 使用 _handle_versioning 逻辑测试版本管理
        svc = AnalysisService(
            fingerprint_service=MagicMock(),
            llm_service=MagicMock(),
            placeholder_registry=MagicMock(),
        )

        created_ids: list[int] = []
        for i in range(n_uploads):
            version, deactivated = svc._handle_versioning(
                law_firm_id=law_firm.pk,
                court_id=court.pk,
                category=category,
                source_type=SourceType.COURT,
                organization_name="",
            )
            template = ExternalTemplate.objects.create(
                name=f"模板v{version}",
                category=category,
                source_type=SourceType.COURT,
                court=court,
                file_path=f"documents/external_templates/{law_firm.pk}/v{version}.docx",
                original_filename=f"v{version}.docx",
                file_size=1024,
                version=version,
                is_active=True,
                law_firm=law_firm,
            )
            created_ids.append(template.pk)

            # 版本号应为 i+1
            assert version == i + 1

            # 前面的版本应已被停用
            if i > 0:
                assert deactivated >= 1

        # 最终只有最后一个版本是 active
        active_count = ExternalTemplate.objects.filter(
            pk__in=created_ids, is_active=True
        ).count()
        assert active_count == 1

        last_template = ExternalTemplate.objects.get(pk=created_ids[-1])
        assert last_template.is_active is True
        assert last_template.version == n_uploads


# ===========================================================================
# Task 16.4: Property 3 — 结构指纹一致性
# **Validates: Requirements 3.1, 3.2**
# ===========================================================================


class TestProperty3FingerprintConsistency(HypothesisTestCase):
    """
    Property 3: 相同 XML 结构（仅文本内容不同）的两个模板应产生相同的
    Structure_Fingerprint。

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        text_a=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
        text_b=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "N"),
        )),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_same_structure_different_text_same_fingerprint(
        self,
        text_a: str,
        text_b: str,
    ) -> None:
        svc = FingerprintService()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            dir_a = tmp_path / "a"
            dir_a.mkdir(parents=True, exist_ok=True)
            docx_a = _create_test_docx(dir_a, text_a)

            dir_b = tmp_path / "b"
            dir_b.mkdir(parents=True, exist_ok=True)
            docx_b = _create_test_docx(dir_b, text_b)

            fp_a = svc.compute_fingerprint(docx_a)
            fp_b = svc.compute_fingerprint(docx_b)

            # 相同结构 → 相同指纹
            assert fp_a == fp_b
            # 指纹是 64 字符的 SHA-256 hex
            assert len(fp_a) == 64

    def test_strip_text_content_removes_text(self) -> None:
        """_strip_text_content 应去除所有文本内容。"""
        svc = FingerprintService()
        xml_input = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Hello World</w:t></w:r></w:p></w:body>"
            "</w:document>"
        )
        result = svc._strip_text_content(xml_input)
        # 结果中不应包含 "Hello World"
        assert "Hello World" not in result
        # 但应保留标签结构
        assert "w:document" in result or "document" in result


# ===========================================================================
# Task 16.5: Property 4 — 指纹匹配复用映射
# **Validates: Requirements 3.3, 3.4**
# ===========================================================================


class TestProperty4FingerprintReuseMappings(HypothesisTestCase):
    """
    Property 4: 新模板指纹匹配已有模板时，应复用映射且 mapping_source
    指向原始模板。

    **Validates: Requirements 3.3, 3.4**
    """

    @given(
        n_mappings=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_fingerprint_match_copies_mappings(
        self,
        n_mappings: int,
    ) -> None:
        from apps.documents.services.external_template.analysis_service import (
            AnalysisService,
        )

        law_firm = _make_law_firm()
        source_template = _make_template(
            law_firm,
            structure_fingerprint="abc123fingerprint",
            status=TemplateStatus.MAPPED,
        )

        # 创建源模板的映射
        for i in range(n_mappings):
            _make_mapping(
                source_template,
                semantic_label=f"字段{i}",
                placeholder_key=f"key_{i}",
                sort_order=i,
            )

        target_template = _make_template(
            law_firm,
            name="目标模板",
            structure_fingerprint="abc123fingerprint",
        )

        svc = AnalysisService(
            fingerprint_service=MagicMock(),
            llm_service=MagicMock(),
            placeholder_registry=MagicMock(),
        )

        created = svc._copy_mappings_from(
            source_template=source_template,
            target_template=target_template,
        )

        # 映射数量应一致
        assert len(created) == n_mappings

        # 所有新映射应关联到目标模板
        for m in created:
            assert m.template_id == target_template.pk

        # 验证映射内容一致
        target_mappings = ExternalTemplateFieldMapping.objects.filter(
            template=target_template
        ).order_by("sort_order")
        source_mappings = ExternalTemplateFieldMapping.objects.filter(
            template=source_template
        ).order_by("sort_order")

        for src, tgt in zip(source_mappings, target_mappings):
            assert tgt.semantic_label == src.semantic_label
            assert tgt.placeholder_key == src.placeholder_key
            assert tgt.fill_type == src.fill_type
            assert tgt.is_confirmed is False  # 复用映射默认未确认


# ===========================================================================
# Task 16.6: Property 5 — 文件校验拒绝非法输入
# **Validates: Requirements 1.2, 1.7**
# ===========================================================================


# 非 .docx 扩展名
_NON_DOCX_EXTENSIONS: list[str] = [
    ".doc", ".pdf", ".txt", ".xlsx", ".pptx", ".zip", ".png", ".jpg",
]


class TestProperty5FileValidation(HypothesisTestCase):
    """
    Property 5: 非 .docx 文件或超过 20MB 的文件应抛出 ValidationError。

    **Validates: Requirements 1.2, 1.7**
    """

    @given(ext=st.sampled_from(_NON_DOCX_EXTENSIONS))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_non_docx_rejected(self, ext: str) -> None:
        from apps.documents.services.external_template.analysis_service import (
            AnalysisService,
        )

        svc = AnalysisService(
            fingerprint_service=MagicMock(),
            llm_service=MagicMock(),
            placeholder_registry=MagicMock(),
        )

        mock_file = MagicMock()
        mock_file.name = f"test{ext}"
        mock_file.size = 1024

        with pytest.raises(ValidationError):
            svc._validate_file(mock_file)

    @given(
        file_size=st.integers(
            min_value=20 * 1024 * 1024 + 1,
            max_value=100 * 1024 * 1024,
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_oversized_file_rejected(self, file_size: int) -> None:
        from apps.documents.services.external_template.analysis_service import (
            AnalysisService,
        )

        svc = AnalysisService(
            fingerprint_service=MagicMock(),
            llm_service=MagicMock(),
            placeholder_registry=MagicMock(),
        )

        mock_file = MagicMock()
        mock_file.name = "test.docx"
        mock_file.size = file_size

        with pytest.raises(ValidationError):
            svc._validate_file(mock_file)

    def test_valid_docx_passes(self) -> None:
        """合法的 .docx 文件应通过校验。"""
        from apps.documents.services.external_template.analysis_service import (
            AnalysisService,
        )

        svc = AnalysisService(
            fingerprint_service=MagicMock(),
            llm_service=MagicMock(),
            placeholder_registry=MagicMock(),
        )

        mock_file = MagicMock()
        mock_file.name = "valid.docx"
        mock_file.size = 1024

        # 不应抛出异常
        svc._validate_file(mock_file)


# ===========================================================================
# Task 16.7: Property 6 — 填充文件名格式
# **Validates: Requirements 5.8, 15.4**
# ===========================================================================


class TestProperty6FillFilenameFormat(HypothesisTestCase):
    """
    Property 6: 生成的文件名应包含模板名称和当事人姓名（如有），
    未确认映射应包含"[未确认]"标记。

    **Validates: Requirements 5.8, 15.4**
    """

    @given(
        template_name=st.text(
            min_size=1, max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
        party_name=st.one_of(
            st.none(),
            st.text(
                min_size=1, max_size=20,
                alphabet=st.characters(whitelist_categories=("L", "N")),
            ),
        ),
        is_confirmed=st.booleans(),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_filename_format(
        self,
        template_name: str,
        party_name: str | None,
        is_confirmed: bool,
    ) -> None:
        from apps.documents.services.external_template.filling_service import (
            FillingService,
        )

        svc = FillingService(placeholder_registry=MagicMock())
        filename = svc._generate_output_filename(
            template_name, party_name, is_confirmed
        )

        # 文件名应以 .docx 结尾
        assert filename.endswith(".docx")

        # 应包含模板名称
        assert template_name in filename

        # 有当事人时应包含当事人姓名
        if party_name:
            assert party_name in filename

        # 未确认时应包含 "[未确认]" 标记
        if not is_confirmed:
            assert "未确认" in filename

        # 已确认时不应包含 "[未确认]" 标记
        if is_confirmed:
            assert "未确认" not in filename


# ===========================================================================
# Task 16.8: Property 7 — 批量填充生成文件数量
# **Validates: Requirements 14.2, 15.5**
# ===========================================================================


class TestProperty7BatchFillFileCount(HypothesisTestCase):
    """
    Property 7: 批量填充应生成 模板数量 × 当事人数量 的文件组合。

    **Validates: Requirements 14.2, 15.5**
    """

    @given(
        n_templates=st.integers(min_value=1, max_value=3),
        n_parties=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_batch_fill_generates_correct_count(
        self,
        n_templates: int,
        n_parties: int,
    ) -> None:
        from apps.documents.services.external_template.filling_service import (
            FillingService,
        )

        law_firm = _make_law_firm()
        case = _make_case()

        template_ids: list[int] = []
        for i in range(n_templates):
            tpl = _make_template(law_firm, name=f"模板{i}")
            template_ids.append(tpl.pk)

        party_ids: list[int] = []
        for _ in range(n_parties):
            party = _make_case_party(case)
            party_ids.append(party.pk)

        # Mock fill_template 使其不实际操作文件
        mock_registry = MagicMock()
        svc = FillingService(placeholder_registry=mock_registry)

        record_counter: int = 0

        def mock_fill_template(
            template_id: int,
            case_id: int,
            party_id: int | None = None,
            custom_values: dict[str, str] | None = None,
            filled_by: Any = None,
        ) -> Any:
            nonlocal record_counter
            record_counter += 1
            tpl = ExternalTemplate.objects.get(pk=template_id)
            record = FillRecord.objects.create(
                case_id=case_id,
                template=tpl,
                party_id=party_id,
                file_path=f"documents/external_filled/{case_id}/fake_{record_counter}.docx",
                original_output_name=f"fake_{record_counter}.docx",
            )
            return record

        with patch.object(svc, "fill_template", side_effect=mock_fill_template):
            with patch.object(svc, "_pack_to_zip", return_value="fake.zip"):
                batch_task = svc.batch_fill(
                    case_id=case.pk,
                    template_ids=template_ids,
                    party_ids=party_ids,
                )

        expected_count = n_templates * n_parties
        assert record_counter == expected_count

        # BatchFillTask 的 summary 应记录正确数量
        assert batch_task.summary_json["total"] == expected_count
        assert batch_task.summary_json["success"] == expected_count


# ===========================================================================
# Task 16.9: Property 8 — FillRecord 历史记录完整性
# **Validates: Requirements 18.1, 18.2**
# ===========================================================================


class TestProperty8FillRecordCompleteness(HypothesisTestCase):
    """
    Property 8: 每次填充操作应创建 FillRecord，包含案件、模板、当事人、
    操作者、时间、文件路径。

    **Validates: Requirements 18.1, 18.2**
    """

    @given(
        has_party=st.booleans(),
        has_operator=st.booleans(),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_fill_record_has_required_fields(
        self,
        has_party: bool,
        has_operator: bool,
    ) -> None:
        law_firm = _make_law_firm()
        case = _make_case()
        template = _make_template(law_firm)

        party = _make_case_party(case) if has_party else None
        lawyer = _make_lawyer(law_firm) if has_operator else None

        record = FillRecord.objects.create(
            case=case,
            template=template,
            party=party,
            filled_by=lawyer,
            file_path="documents/external_filled/1/test.docx",
            original_output_name="test.docx",
            report_json={"total_fields": 5, "filled_count": 3},
        )

        fetched = FillRecord.objects.get(pk=record.pk)

        # 必填字段
        assert fetched.case_id == case.pk
        assert fetched.template_id == template.pk
        assert fetched.file_path != ""
        assert fetched.filled_at is not None

        # 可选字段
        if has_party:
            assert fetched.party_id == party.pk  # type: ignore[union-attr]
        else:
            assert fetched.party_id is None

        if has_operator:
            assert fetched.filled_by_id == lawyer.pk  # type: ignore[union-attr]
        else:
            assert fetched.filled_by_id is None

        # 默认排序应为 -filled_at
        assert FillRecord._meta.ordering == ["-filled_at"]


# ===========================================================================
# Task 16.10: Property 9 — 法院模板匹配含上级法院回退
# **Validates: Requirements 7.1, 7.2**
# ===========================================================================


class TestProperty9CourtFallback(HypothesisTestCase):
    """
    Property 9: 案件法院无模板时，应返回上级法院的模板。

    **Validates: Requirements 7.1, 7.2**
    """

    @given(
        category=st.sampled_from([c.value for c in TemplateCategory]),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_parent_court_fallback(
        self,
        category: str,
    ) -> None:
        from apps.documents.services.external_template.matching_service import (
            MatchingService,
        )

        law_firm = _make_law_firm()
        parent_court = _make_court(name="上级法院")
        child_court = _make_court(parent=parent_court, name="下级法院")

        # 仅在上级法院创建模板
        parent_template = _make_template(
            law_firm,
            court=parent_court,
            category=category,
            status=TemplateStatus.CONFIRMED,
            name="上级法院模板",
        )

        svc = MatchingService()
        result = svc.match_by_court(child_court.pk, law_firm.pk)

        # 应返回上级法院的模板
        all_templates = [t for templates in result.values() for t in templates]
        assert len(all_templates) >= 1

        template_ids = [t.pk for t in all_templates]
        assert parent_template.pk in template_ids

    def test_direct_court_match(self) -> None:
        """法院有模板时应直接返回。"""
        from apps.documents.services.external_template.matching_service import (
            MatchingService,
        )

        law_firm = _make_law_firm()
        court = _make_court()
        template = _make_template(
            law_firm,
            court=court,
            category=TemplateCategory.PROPERTY_DECLARATION,
        )

        svc = MatchingService()
        result = svc.match_by_court(court.pk, law_firm.pk)

        all_templates = [t for templates in result.values() for t in templates]
        assert len(all_templates) == 1
        assert all_templates[0].pk == template.pk

    def test_no_court_no_parent_returns_empty(self) -> None:
        """无模板且无上级法院时应返回空。"""
        from apps.documents.services.external_template.matching_service import (
            MatchingService,
        )

        law_firm = _make_law_firm()
        court = _make_court()  # 无上级法院

        svc = MatchingService()
        result = svc.match_by_court(court.pk, law_firm.pk)
        assert result == {}


# ===========================================================================
# Task 16.11: Property 10 — 数据隔离
# **Validates: Requirements 8.1**
# ===========================================================================


class TestProperty10DataIsolation(HypothesisTestCase):
    """
    Property 10: 不同律所的模板应互不可见。

    **Validates: Requirements 8.1**
    """

    @given(
        n_templates_a=st.integers(min_value=1, max_value=3),
        n_templates_b=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_templates_isolated_by_law_firm(
        self,
        n_templates_a: int,
        n_templates_b: int,
    ) -> None:
        from apps.documents.services.external_template.matching_service import (
            MatchingService,
        )

        law_firm_a = _make_law_firm(name="律所A")
        law_firm_b = _make_law_firm(name="律所B")
        court = _make_court()

        # 律所A的模板
        ids_a: list[int] = []
        for i in range(n_templates_a):
            tpl = _make_template(
                law_firm_a,
                court=court,
                name=f"律所A模板{i}",
                category=TemplateCategory.PROPERTY_DECLARATION,
            )
            ids_a.append(tpl.pk)

        # 律所B的模板
        ids_b: list[int] = []
        for i in range(n_templates_b):
            tpl = _make_template(
                law_firm_b,
                court=court,
                name=f"律所B模板{i}",
                category=TemplateCategory.PROPERTY_DECLARATION,
            )
            ids_b.append(tpl.pk)

        svc = MatchingService()

        # 律所A只能看到自己的模板
        result_a = svc.match_by_court(court.pk, law_firm_a.pk)
        all_a = [t for templates in result_a.values() for t in templates]
        a_pks = {t.pk for t in all_a}
        assert a_pks == set(ids_a)
        assert not a_pks.intersection(set(ids_b))

        # 律所B只能看到自己的模板
        result_b = svc.match_by_court(court.pk, law_firm_b.pk)
        all_b = [t for templates in result_b.values() for t in templates]
        b_pks = {t.pk for t in all_b}
        assert b_pks == set(ids_b)
        assert not b_pks.intersection(set(ids_a))

    def test_direct_query_isolation(self) -> None:
        """直接查询也应按律所隔离。"""
        law_firm_a = _make_law_firm(name="隔离测试A")
        law_firm_b = _make_law_firm(name="隔离测试B")

        tpl_a = _make_template(law_firm_a, name="A的模板")
        tpl_b = _make_template(law_firm_b, name="B的模板")

        # 按律所A查询
        qs_a = ExternalTemplate.objects.filter(
            law_firm=law_firm_a, is_active=True
        )
        assert qs_a.count() == 1
        assert qs_a.first().pk == tpl_a.pk  # type: ignore[union-attr]

        # 按律所B查询
        qs_b = ExternalTemplate.objects.filter(
            law_firm=law_firm_b, is_active=True
        )
        assert qs_b.count() == 1
        assert qs_b.first().pk == tpl_b.pk  # type: ignore[union-attr]
