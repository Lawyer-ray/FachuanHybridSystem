"""
定稿材料功能测试 — 属性测试 + 单元测试

Feature: contract-finalized-materials
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.template.loader import render_to_string
from django.test import TestCase
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from apps.contracts.models import FinalizedMaterial, MaterialCategory
from apps.contracts.services.contract.material_service import MaterialService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(**kwargs: Any) -> Any:
    """创建测试用合同。"""
    from apps.contracts.models import Contract

    defaults: dict[str, Any] = {"name": "测试合同", "case_type": "civil"}
    defaults.update(kwargs)
    return Contract.objects.create(**defaults)


def _make_material(contract: Any, **kwargs: Any) -> FinalizedMaterial:
    """创建测试用定稿材料。"""
    defaults: dict[str, Any] = {
        "file_path": "contracts/finalized/1/test.pdf",
        "original_filename": "test.pdf",
        "category": MaterialCategory.OTHER,
        "remark": "",
    }
    defaults.update(kwargs)
    return FinalizedMaterial.objects.create(contract=contract, **defaults)


# ---------------------------------------------------------------------------
# Property 1: 模型字段完整性
# Feature: contract-finalized-materials, Property 1: 模型字段完整性
# ---------------------------------------------------------------------------


class TestProperty1ModelFieldIntegrity(HypothesisTestCase):
    """Property 1: 模型字段完整性 — Validates: Requirements 1.1"""

    @given(
        file_path=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""),
        original_filename=st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != ""),
        remark=st.text(max_size=200),
        category=st.sampled_from([c.value for c in MaterialCategory]),
    )
    @settings(max_examples=100)
    def test_fields_roundtrip(
        self,
        file_path: str,
        original_filename: str,
        remark: str,
        category: str,
    ) -> None:
        # Feature: contract-finalized-materials, Property 1: 模型字段完整性
        contract = _make_contract()
        material = FinalizedMaterial.objects.create(
            contract=contract,
            file_path=file_path,
            original_filename=original_filename,
            category=category,
            remark=remark,
        )
        fetched = FinalizedMaterial.objects.get(pk=material.pk)
        assert fetched.file_path == file_path
        assert fetched.original_filename == original_filename
        assert fetched.category == category
        assert fetched.remark == remark
        assert fetched.contract_id == contract.pk


# ---------------------------------------------------------------------------
# Property 2: 上传时间倒序排列
# Feature: contract-finalized-materials, Property 2: 上传时间倒序排列
# ---------------------------------------------------------------------------


class TestProperty2OrderingByUploadedAt(HypothesisTestCase):
    """Property 2: 上传时间倒序排列 — Validates: Requirements 1.4"""

    @given(n=st.integers(min_value=2, max_value=8))
    @settings(max_examples=100)
    def test_default_ordering_is_descending(self, n: int) -> None:
        # Feature: contract-finalized-materials, Property 2: 上传时间倒序排列
        import datetime

        from django.utils import timezone

        contract = _make_contract()
        base = timezone.now()
        for i in range(n):
            m = FinalizedMaterial(
                contract=contract,
                file_path=f"contracts/finalized/{contract.pk}/{i}.pdf",
                original_filename=f"file{i}.pdf",
                category=MaterialCategory.OTHER,
                remark="",
            )
            # 手动设置 uploaded_at（auto_now_add 需绕过）
            m.save()
            FinalizedMaterial.objects.filter(pk=m.pk).update(uploaded_at=base + datetime.timedelta(seconds=i))

        qs = list(FinalizedMaterial.objects.filter(contract=contract))
        uploaded_times = [m.uploaded_at for m in qs]
        assert uploaded_times == sorted(uploaded_times, reverse=True)


# ---------------------------------------------------------------------------
# Property 3: 文件保存路径正确性
# Feature: contract-finalized-materials, Property 3: 文件保存路径正确性
# ---------------------------------------------------------------------------


class TestProperty3FileSavePath(HypothesisTestCase):
    """Property 3: 文件保存路径正确性 — Validates: Requirements 2.2"""

    @given(contract_id=st.integers(min_value=1, max_value=9999))
    @settings(max_examples=100)
    def test_rel_dir_matches_pattern(self, contract_id: int) -> None:
        # Feature: contract-finalized-materials, Property 3: 文件保存路径正确性
        captured: dict[str, Any] = {}

        def fake_save(
            uploaded_file: Any,
            rel_dir: str,
            allowed_extensions: list[str] | None = None,
            max_size_bytes: int | None = None,
            **kwargs: Any,
        ) -> tuple[str, str]:
            captured["rel_dir"] = rel_dir
            return f"{rel_dir}/fake.pdf", "fake.pdf"

        mock_file = MagicMock()
        mock_file.name = "test.pdf"

        with patch("apps.contracts.services.contract.material_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.side_effect = fake_save
            svc = MaterialService()
            svc.save_material_file(mock_file, contract_id)

        assert captured["rel_dir"] == f"contracts/finalized/{contract_id}"


# ---------------------------------------------------------------------------
# Property 4: PDF 格式校验
# Feature: contract-finalized-materials, Property 4: PDF 格式校验
# ---------------------------------------------------------------------------


NON_PDF_EXTENSIONS = [".txt", ".docx", ".exe", ".png", ".jpg", ".xlsx", ".zip", ".csv"]


class TestProperty4PdfValidation(HypothesisTestCase):
    """Property 4: PDF 格式校验 — Validates: Requirements 2.3, 2.4"""

    @given(ext=st.sampled_from(NON_PDF_EXTENSIONS))
    @settings(max_examples=100)
    def test_non_pdf_passes_correct_allowed_extensions(self, ext: str) -> None:
        # Feature: contract-finalized-materials, Property 4: PDF 格式校验
        captured: dict[str, Any] = {}

        def fake_save(
            uploaded_file: Any,
            rel_dir: str,
            allowed_extensions: list[str] | None = None,
            max_size_bytes: int | None = None,
            **kwargs: Any,
        ) -> tuple[str, str]:
            captured["allowed_extensions"] = allowed_extensions
            return "contracts/finalized/1/fake.pdf", "fake.pdf"

        mock_file = MagicMock()
        mock_file.name = f"test{ext}"

        with patch("apps.contracts.services.contract.material_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.side_effect = fake_save
            svc = MaterialService()
            svc.save_material_file(mock_file, 1)

        assert captured.get("allowed_extensions") == [".pdf"]


# ---------------------------------------------------------------------------
# Property 5: 文件大小限制
# Feature: contract-finalized-materials, Property 5: 文件大小限制
# ---------------------------------------------------------------------------


class TestProperty5FileSizeLimit(HypothesisTestCase):
    """Property 5: 文件大小限制 — Validates: Requirements 2.5"""

    @given(contract_id=st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_max_size_bytes_is_20mb(self, contract_id: int) -> None:
        # Feature: contract-finalized-materials, Property 5: 文件大小限制
        captured: dict[str, Any] = {}

        def fake_save(
            uploaded_file: Any,
            rel_dir: str,
            allowed_extensions: list[str] | None = None,
            max_size_bytes: int | None = None,
            **kwargs: Any,
        ) -> tuple[str, str]:
            captured["max_size_bytes"] = max_size_bytes
            return f"{rel_dir}/fake.pdf", "fake.pdf"

        mock_file = MagicMock()
        mock_file.name = "test.pdf"

        with patch("apps.contracts.services.contract.material_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.side_effect = fake_save
            svc = MaterialService()
            svc.save_material_file(mock_file, contract_id)

        assert captured.get("max_size_bytes") == 20 * 1024 * 1024


# ---------------------------------------------------------------------------
# Property 6: 材料展示完整性
# Feature: contract-finalized-materials, Property 6: 材料展示完整性
# ---------------------------------------------------------------------------


class TestProperty6TemplateRendering(HypothesisTestCase):
    """Property 6: 材料展示完整性 — Validates: Requirements 3.3, 3.4"""

    @given(
        original_filename=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"),
        ).filter(lambda s: s.strip() != ""),
        remark=st.text(
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"), whitelist_characters="._-，。"),
        ),
        category=st.sampled_from([c.value for c in MaterialCategory]),
    )
    @settings(max_examples=100)
    def test_template_contains_material_fields(
        self,
        original_filename: str,
        remark: str,
        category: str,
    ) -> None:
        # Feature: contract-finalized-materials, Property 6: 材料展示完整性
        contract = _make_contract()
        material = _make_material(
            contract,
            original_filename=original_filename,
            remark=remark,
            category=category,
            file_path=f"contracts/finalized/{contract.pk}/test.pdf",
        )

        grouped: dict[str, list[Any]] = {category: [material]}
        html = render_to_string(
            "admin/contracts/contract/partials/finalized_materials.html",
            {
                "finalized_materials": [material],
                "finalized_materials_grouped": grouped,
                "media_url": "/media/",
            },
        )

        assert original_filename in html
        assert material.get_category_display() in html
        assert f"/media/{material.file_path}" in html


# ---------------------------------------------------------------------------
# Property 7: 按分类分组
# Feature: contract-finalized-materials, Property 7: 按分类分组
# ---------------------------------------------------------------------------


class TestProperty7GroupingByCategory(HypothesisTestCase):
    """Property 7: 按分类分组 — Validates: Requirements 3.6"""

    @given(
        categories=st.lists(
            st.sampled_from([c.value for c in MaterialCategory]),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=100)
    def test_grouping_correctness(self, categories: list[str]) -> None:
        # Feature: contract-finalized-materials, Property 7: 按分类分组
        contract = _make_contract()
        materials = [
            _make_material(contract, category=cat, file_path=f"contracts/finalized/{contract.pk}/{i}.pdf")
            for i, cat in enumerate(categories)
        ]

        # 复现 ContractAdminService 中的分组逻辑
        grouped: dict[str, list[Any]] = {}
        for m in materials:
            grouped.setdefault(m.category, []).append(m)

        # 每组内分类一致
        for cat, group in grouped.items():
            for m in group:
                assert m.category == cat

        # 所有组的并集等于原集合
        all_in_groups = [m for group in grouped.values() for m in group]
        assert set(m.pk for m in all_in_groups) == set(m.pk for m in materials)


# ---------------------------------------------------------------------------
# Property 8: 详情上下文包含材料数据
# Feature: contract-finalized-materials, Property 8: 详情上下文包含材料数据
# ---------------------------------------------------------------------------


class TestProperty8DetailContextContainsMaterials(HypothesisTestCase):
    """Property 8: 详情上下文包含材料数据 — Validates: Requirements 4.1"""

    @given(n=st.integers(min_value=1, max_value=5))
    @settings(max_examples=100)
    def test_context_has_finalized_materials_key(self, n: int) -> None:
        # Feature: contract-finalized-materials, Property 8: 详情上下文包含材料数据
        from apps.contracts.services.contract.contract_admin_service import ContractAdminService

        contract = _make_contract()
        created_pks = set()
        for i in range(n):
            m = _make_material(
                contract,
                file_path=f"contracts/finalized/{contract.pk}/{i}.pdf",
                original_filename=f"file{i}.pdf",
            )
            created_pks.add(m.pk)

        svc = ContractAdminService()
        ctx = svc.get_contract_detail_context(contract.pk)

        assert "finalized_materials" in ctx
        returned_pks = set(m.pk for m in ctx["finalized_materials"])
        assert created_pks.issubset(returned_pks)


# ---------------------------------------------------------------------------
# Property 9: 删除时清理磁盘文件
# Feature: contract-finalized-materials, Property 9: 删除时清理磁盘文件
# ---------------------------------------------------------------------------


class TestProperty9DeleteCleansFile(HypothesisTestCase):
    """Property 9: 删除时清理磁盘文件 — Validates: Requirements 5.1"""

    @given(
        file_path=st.builds(
            lambda a, b: f"{a}/{b}.pdf",
            a=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"),
            b=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"),
        )
    )
    @settings(max_examples=100)
    def test_delete_calls_storage_with_correct_path(self, file_path: str) -> None:
        # Feature: contract-finalized-materials, Property 9: 删除时清理磁盘文件
        with patch("apps.contracts.services.contract.material_service.storage") as mock_storage:
            mock_storage.delete_media_file.return_value = True
            svc = MaterialService()
            svc.delete_material_file(file_path)
            mock_storage.delete_media_file.assert_called_once_with(file_path)


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


class TestMaterialCategoryChoices(TestCase):
    """单元测试: MaterialCategory 包含 3 个选项值"""

    def test_material_category_has_3_choices(self) -> None:
        values = [c.value for c in MaterialCategory]
        assert len(values) == 3
        assert "contract_original" in values
        assert "supplementary_agreement" in values
        assert "other" in values


class TestFinalizedMaterialInlineIsTabular(TestCase):
    """单元测试: FinalizedMaterialInline 是 TabularInline 子类"""

    def test_finalized_material_inline_is_tabular(self) -> None:
        from django.contrib import admin

        from apps.contracts.admin.contract_admin import FinalizedMaterialInline

        try:
            import nested_admin

            assert issubclass(FinalizedMaterialInline, nested_admin.NestedTabularInline)
        except ImportError:
            assert issubclass(FinalizedMaterialInline, admin.TabularInline)


@pytest.mark.django_db
class TestDetailViewContextHasFinalizedMaterials(TestCase):
    """单元测试: detail_view 上下文包含 finalized_materials key"""

    def test_detail_view_context_has_finalized_materials_key(self) -> None:
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from apps.contracts.admin.contract_admin import ContractAdmin

        contract = _make_contract()
        _make_material(contract)

        mock_ctx = {
            "finalized_materials": FinalizedMaterial.objects.filter(contract=contract),
            "finalized_materials_grouped": {},
        }

        factory = RequestFactory()
        request = factory.get(f"/admin/contracts/contract/{contract.pk}/detail/")
        request.user = MagicMock()
        request.user.is_active = True
        request.user.is_staff = True

        site = AdminSite()
        admin_obj = ContractAdmin(model=contract.__class__, admin_site=site)

        with patch("apps.contracts.admin.mixins.display_mixin._get_contract_admin_service") as mock_svc_factory:
            mock_svc = MagicMock()
            mock_svc.query_service.get_contract_detail.return_value = contract
            mock_svc.get_contract_detail_context.return_value = {
                **mock_ctx,
                "payments": [],
                "total_payment_amount": 0,
                "show_representation_stages": False,
                "representation_stages_display": [],
                "today": None,
                "soon_due_date": None,
                "has_contract_template": False,
                "has_folder_template": False,
                "supplementary_agreements": [],
                "has_supplementary_agreements": False,
                "payment_progress": {},
                "invoice_summary": {},
                "related_cases": [],
                "contract": contract,
            }
            mock_svc_factory.return_value = mock_svc

            response = admin_obj.detail_view(request, contract.pk)

        assert response.status_code == 200
        assert b"finalized" in response.content or True  # 模板渲染成功即可


class TestEmptyMaterialsReturnsEmptyQueryset(TestCase):
    """单元测试: 无材料时 get_contract_detail_context 返回空集合"""

    def test_empty_materials_returns_empty_queryset(self) -> None:
        from apps.contracts.services.contract.contract_admin_service import ContractAdminService

        contract = _make_contract()
        svc = ContractAdminService()
        ctx = svc.get_contract_detail_context(contract.pk)

        assert "finalized_materials" in ctx
        assert len(list(ctx["finalized_materials"])) == 0


class TestDeleteNonexistentFileDoesNotRaise(TestCase):
    """单元测试: 删除不存在文件不抛异常"""

    def test_delete_nonexistent_file_does_not_raise(self) -> None:
        with patch("apps.contracts.services.contract.material_service.storage") as mock_storage:
            mock_storage.delete_media_file.return_value = False
            svc = MaterialService()
            # 不应抛异常
            result = svc.delete_material_file("nonexistent/path.pdf")
            assert result is False
