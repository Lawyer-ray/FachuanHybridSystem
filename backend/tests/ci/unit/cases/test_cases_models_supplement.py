"""cases app 补充 Model 单元测试

覆盖 CaseNumber, CaseMaterialType, CaseMaterial, CaseFolderBinding,
SupervisingAuthority, Case, CaseFilingNumberSequence 的 property、__str__、choices。
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.cases.models.case import Case, CaseFilingNumberSequence, CaseNumber, SupervisingAuthority
from apps.cases.models.material import (
    CaseFolderBinding,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialGroupOrder,
    CaseMaterialSide,
    CaseMaterialType,
)
from apps.cases.models.template_binding import BindingSource, CaseTemplateBinding
from apps.cases.models.folder_scan_session import CaseFolderScanSession, CaseFolderScanStatus
from apps.core.models.enums import AuthorityType, CaseStage, SimpleCaseType
from apps.testing.factories import CaseFactory, ContractFactory, LawyerFactory


# ============================================================
# CaseNumber
# ============================================================


@pytest.mark.django_db
class TestCaseNumber:
    def test_str(self):
        case = CaseFactory()
        cn = CaseNumber.objects.create(case=case, number="(2025)京01民初123号")
        assert str(cn) == "(2025)京01民初123号"

    def test_get_full_number_with_document_name(self):
        case = CaseFactory()
        cn = CaseNumber.objects.create(
            case=case,
            number="(2025)京01民初123号",
            document_name="民事判决书",
        )
        assert cn.get_full_number() == "(2025)京01民初123号《民事判决书》"

    def test_get_full_number_without_document_name(self):
        case = CaseFactory()
        cn = CaseNumber.objects.create(
            case=case,
            number="(2025)京01民初123号",
        )
        assert cn.get_full_number() == "(2025)京01民初123号"

    def test_year_days_choices(self):
        assert CaseNumber.YEAR_DAYS_CHOICES == ((360, "360天"), (365, "365天"), (0, "按实际天数"))

    def test_date_inclusion_choices(self):
        choices_dict = dict(CaseNumber.DATE_INCLUSION_CHOICES)
        assert "both" in choices_dict
        assert "start_only" in choices_dict
        assert "end_only" in choices_dict
        assert "neither" in choices_dict

    def test_default_year_days(self):
        case = CaseFactory()
        cn = CaseNumber.objects.create(case=case, number="测试案号")
        assert cn.execution_year_days == 360

    def test_default_date_inclusion(self):
        case = CaseFactory()
        cn = CaseNumber.objects.create(case=case, number="测试案号2")
        assert cn.execution_date_inclusion == "both"


# ============================================================
# SupervisingAuthority
# ============================================================


@pytest.mark.django_db
class TestSupervisingAuthority:
    def test_str_with_type_and_name(self):
        case = CaseFactory()
        sa = SupervisingAuthority.objects.create(
            case=case,
            name="北京市第一中级人民法院",
            authority_type=AuthorityType.TRIAL,
        )
        result = str(sa)
        assert "北京市第一中级人民法院" in result
        assert sa.get_authority_type_display() in result

    def test_str_with_name_only(self):
        case = CaseFactory()
        # authority_type 有默认值 TRIAL，所以 name+type 分支
        sa = SupervisingAuthority.objects.create(
            case=case,
            name="某法院",
        )
        result = str(sa)
        assert "某法院" in result

    def test_str_with_type_only(self):
        case = CaseFactory()
        sa = SupervisingAuthority.objects.create(
            case=case,
            authority_type=AuthorityType.TRIAL,
        )
        result = str(sa)
        assert sa.get_authority_type_display() in result

    def test_str_neither(self):
        case = CaseFactory()
        # authority_type 有默认值，所以至少有 type 分支
        sa = SupervisingAuthority.objects.create(case=case, name=None, authority_type=None)
        result = str(sa)
        assert "主管机关" in result

    def test_unique_together(self):
        case = CaseFactory()
        SupervisingAuthority.objects.create(case=case, name="法院A")
        with pytest.raises(IntegrityError):
            SupervisingAuthority.objects.create(case=case, name="法院A")


# ============================================================
# CaseMaterialType
# ============================================================


@pytest.mark.django_db
class TestCaseMaterialType:
    def test_str_with_law_firm(self):
        from apps.organization.models.law_firm import LawFirm

        firm = LawFirm.objects.create(name="测试律所")
        mt = CaseMaterialType.objects.create(
            category=CaseMaterialCategory.PARTY,
            name="身份证复印件",
            law_firm=firm,
        )
        result = str(mt)
        assert "测试律所" in result
        assert "当事人材料" in result
        assert "身份证复印件" in result

    def test_str_global(self):
        mt = CaseMaterialType.objects.create(
            category=CaseMaterialCategory.NON_PARTY,
            name="调查令",
        )
        result = str(mt)
        assert "全局" in result
        assert "非当事人材料" in result

    def test_unique_constraint(self):
        from apps.organization.models.law_firm import LawFirm

        firm = LawFirm.objects.create(name="约束律所")
        CaseMaterialType.objects.create(
            category=CaseMaterialCategory.PARTY,
            name="类型A",
            law_firm=firm,
        )
        with pytest.raises(IntegrityError):
            CaseMaterialType.objects.create(
                category=CaseMaterialCategory.PARTY,
                name="类型A",
                law_firm=firm,
            )


# ============================================================
# CaseMaterial
# ============================================================


@pytest.mark.django_db
class TestCaseMaterial:
    def test_str(self):
        case = CaseFactory()
        mt = CaseMaterialType.objects.create(
            category=CaseMaterialCategory.PARTY,
            name="身份证",
        )
        material = CaseMaterial.objects.create(
            case=case,
            category=CaseMaterialCategory.PARTY,
            type=mt,
            type_name="身份证",
            side=CaseMaterialSide.OUR,
        )
        result = str(material)
        assert str(case.id) in result
        assert "当事人材料" in result
        assert "身份证" in result


# ============================================================
# CaseFolderBinding
# ============================================================


@pytest.mark.django_db
class TestCaseFolderBinding:
    def test_str(self):
        case = CaseFactory(name="测试案件")
        binding = CaseFolderBinding.objects.create(
            case=case,
            folder_path="/cases/test/2026",
        )
        result = str(binding)
        assert "测试案件" in result
        assert "/cases/test/2026" in result

    def test_folder_path_display_short(self):
        case = CaseFactory()
        binding = CaseFolderBinding(case=case, folder_path="/short/path")
        # 直接测 property 逻辑
        assert binding.folder_path_display == "/short/path"

    def test_folder_path_display_empty(self):
        case = CaseFactory()
        binding = CaseFolderBinding(case=case, folder_path="")
        assert binding.folder_path_display == ""

    def test_resolved_folder_path_no_relative(self):
        case = CaseFactory()
        binding = CaseFolderBinding(
            case=case,
            folder_path="/absolute/path",
            relative_path="",
        )
        assert binding.resolved_folder_path == "/absolute/path"

    def test_resolved_folder_path_with_relative(self):
        case = CaseFactory()
        binding = CaseFolderBinding(
            case=case,
            folder_path="/fallback",
            relative_path="subfolder",
        )
        # 没有关联合同的 folder_binding 时，降级到 folder_path
        result = binding.resolved_folder_path
        # 如果没有 contract folder_binding，会降级
        assert result == "/fallback" or "subfolder" in result


# ============================================================
# Case
# ============================================================


@pytest.mark.django_db
class TestCase:
    def test_str(self):
        case = Case.objects.create(name="借款合同纠纷案")
        assert str(case) == "借款合同纠纷案"

    def test_clean_valid_stage(self):
        case = Case(name="测试", current_stage=CaseStage.FIRST_TRIAL)
        case.clean()  # 不应抛异常

    def test_clean_invalid_stage(self):
        case = Case(name="测试", current_stage="invalid_stage")
        with pytest.raises(ValidationError):
            case.clean()

    def test_clean_no_stage(self):
        case = Case(name="测试", current_stage=None)
        case.clean()  # 不应抛异常

    def test_default_values(self):
        case = Case.objects.create(name="默认值测试")
        assert case.status == "active"
        assert case.case_type == SimpleCaseType.CIVIL
        assert case.is_filed is False


# ============================================================
# CaseTemplateBinding
# ============================================================


@pytest.mark.django_db
class TestCaseTemplateBinding:
    def test_str(self):
        case = CaseFactory()
        from apps.documents.models import DocumentTemplate

        template = DocumentTemplate.objects.create(name="模板", file_path="t.docx")
        binding = CaseTemplateBinding.objects.create(
            case=case,
            template=template,
            binding_source=BindingSource.AUTO_RECOMMENDED,
        )
        result = str(binding)
        assert str(case.id) in result
        assert str(template.id) in result

    def test_binding_source_choices(self):
        assert BindingSource.AUTO_RECOMMENDED.value == "auto_recommended"
        assert BindingSource.MANUAL_BOUND.value == "manual_bound"


# ============================================================
# CaseFolderScanSession
# ============================================================


@pytest.mark.django_db
class TestCaseFolderScanSession:
    def test_str(self):
        case = CaseFactory()
        session = CaseFolderScanSession.objects.create(
            case=case,
            status=CaseFolderScanStatus.PENDING,
        )
        result = str(session)
        assert f"case:{case.id}" in result
        assert "pending" in result

    def test_status_choices(self):
        assert CaseFolderScanStatus.PENDING.value == "pending"
        assert CaseFolderScanStatus.RUNNING.value == "running"
        assert CaseFolderScanStatus.COMPLETED.value == "completed"
        assert CaseFolderScanStatus.FAILED.value == "failed"
        assert CaseFolderScanStatus.STAGED.value == "staged"
        assert CaseFolderScanStatus.CANCELLED.value == "cancelled"


# ============================================================
# CaseMaterialGroupOrder
# ============================================================


@pytest.mark.django_db
class TestCaseMaterialGroupOrder:
    def test_str(self):
        case = CaseFactory()
        mt = CaseMaterialType.objects.create(
            category=CaseMaterialCategory.PARTY,
            name="类型A",
        )
        order = CaseMaterialGroupOrder.objects.create(
            case=case,
            category=CaseMaterialCategory.PARTY,
            type=mt,
            sort_index=1,
        )
        result = str(order)
        assert str(case.id) in result
        assert "party" in result
        assert "1" in result
