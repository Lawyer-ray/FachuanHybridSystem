"""槽位落位体系测试。

覆盖：
- SlotResolutionService：kind→路径派生 / 槽位优先旧路径兜底 / 虚拟绑定 skip
- iter_effective_bindings：存量绑定 + 槽位虚拟绑定（新增骨架零绑定操作）
- get_document_placements：槽位声明模板无绑定行也能落位（生成入口切换）
- 回填命令：词表种子 / kind 回填 / folder_slot 回填（幂等、dry-run）
- duplicate_template：复制模板连带复制绑定
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from apps.documents.models import DocumentTemplate, DocumentTemplateFolderBinding, FolderSlot, FolderTemplate
from apps.documents.models.choices import DocumentCaseFileSubType, DocumentTemplateType
from apps.documents.services.generation.folder_generation_service import FolderGenerationService
from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService
from apps.documents.services.template.slot_resolution_service import RESOLVED_BY_SLOT, SlotResolutionService


def make_structure() -> dict[str, Any]:
    """复刻真实骨架形态：根在 structure.children 顶层，叶子带 kind"""
    return {
        "children": [
            {
                "id": "n_root",
                "name": "一审",
                "children": [
                    {
                        "id": "n_group",
                        "name": "1-立案材料",
                        "children": [
                            {"id": "n_complaint", "name": "1-起诉状和反诉答辩状", "children": [], "kind": "complaint"},
                            {"id": "n_id", "name": "2-当事人身份证明", "children": [], "kind": "identity_proof"},
                            {"id": "n_poa", "name": "3-委托材料", "children": [], "kind": "power_of_attorney"},
                        ],
                    },
                    {"id": "n_mail", "name": "4-邮件往来", "children": [], "kind": "correspondence"},
                ],
            }
        ]
    }


@pytest.fixture
def slot_poa(db: FolderSlot) -> FolderSlot:
    return FolderSlot.objects.create(key="power_of_attorney", name="委托材料")


@pytest.fixture
def folder_tpl(db: FolderTemplate) -> FolderTemplate:
    return FolderTemplate.objects.create(
        name="测试骨架",
        template_type="case",
        case_types=["civil"],
        structure=make_structure(),
    )


@pytest.fixture
def doc_poa(db: DocumentTemplate) -> DocumentTemplate:
    return DocumentTemplate.objects.create(
        name="授权委托书",
        template_type=DocumentTemplateType.CASE,
        case_sub_type=DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS,
        case_types=["all"],
        file_path="poa.docx",
    )


@pytest.fixture
def doc_contract(db: DocumentTemplate) -> DocumentTemplate:
    """合同型模板（合同侧落位按 contract_types 过滤，故用合同模板走该入口）"""
    return DocumentTemplate.objects.create(
        name="测试合同模板",
        template_type=DocumentTemplateType.CONTRACT,
        contract_types=["all"],
        file_path="contract.docx",
    )


class TestFindSlotPaths:
    def test_finds_nested_slot_path(self, folder_tpl: FolderTemplate) -> None:
        paths = SlotResolutionService().find_slot_paths(folder_tpl, "power_of_attorney")
        assert paths == [["一审", "1-立案材料", "3-委托材料"]]

    def test_miss_returns_empty(self, folder_tpl: FolderTemplate) -> None:
        assert SlotResolutionService().find_slot_paths(folder_tpl, "nope") == []

    def test_multiple_hits_all_returned(self, db: Any) -> None:
        tpl = FolderTemplate.objects.create(
            name="双槽",
            template_type="case",
            structure={
                "children": [
                    {"id": "a", "name": "A", "children": [{"id": "a1", "name": "委托材料", "children": [], "kind": "power_of_attorney"}]},
                    {"id": "b", "name": "B", "children": [{"id": "b1", "name": "5-委托材料", "children": [], "kind": "power_of_attorney"}]},
                ]
            },
        )
        paths = SlotResolutionService().find_slot_paths(tpl, "power_of_attorney")
        assert len(paths) == 2
        assert paths[0] == ["A", "委托材料"]
        assert paths[1] == ["B", "5-委托材料"]


class TestResolveBindingPath:
    def test_slot_hit_derives_path(self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate) -> None:
        doc_poa.folder_slot = slot_poa
        binding = DocumentTemplateFolderBinding(
            document_template=doc_poa,
            folder_template=folder_tpl,
            folder_node_id="n_poa",
            folder_node_path="一审/1-立案材料/3-委托材料",
        )
        result = SlotResolutionService().resolve_binding_path(binding)
        assert result.path == "一审/1-立案材料/3-委托材料"
        assert result.resolved_by == RESOLVED_BY_SLOT

    def test_slot_rename_changes_derived_path(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        """结构改名后派生路径自动跟随（存量存储路径腐烂问题的回归）"""
        doc_poa.folder_slot = slot_poa
        folder_tpl.structure["children"][0]["children"][0]["children"][2]["name"] = "3-授权与委托文件"  # type: ignore[index]
        folder_tpl.save(update_fields=["structure", "updated_at"])
        binding = DocumentTemplateFolderBinding(
            document_template=doc_poa,
            folder_template=folder_tpl,
            folder_node_id="n_poa",
            folder_node_path="一审/1-立案材料/3-委托材料",
        )
        result = SlotResolutionService().resolve_binding_path(binding)
        assert result.path == "一审/1-立案材料/3-授权与委托文件"

    def test_slot_miss_saved_binding_falls_back_to_legacy(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        doc_poa.folder_slot = slot_poa
        binding = DocumentTemplateFolderBinding.objects.create(
            document_template=doc_poa,
            folder_template=folder_tpl,
            folder_node_id="n_mail",
            folder_node_path="一审/4-邮件往来",
        )
        # 骨架不含 identity_proof 之外的其它槽位 → 换一个未提供的槽位
        slot_missing = FolderSlot.objects.create(key="service_address", name="送达地址确认书")
        doc_poa.folder_slot = slot_missing
        result = SlotResolutionService().resolve_binding_path(binding)
        assert result.path == "一审/4-邮件往来"
        assert result.skip is False

    def test_slot_miss_virtual_binding_skips(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        doc_poa.folder_slot = slot_poa
        # 换成骨架未提供的槽位，且构造未保存的虚拟绑定
        slot_missing = FolderSlot.objects.create(key="service_address", name="送达地址确认书")
        doc_poa.folder_slot = slot_missing
        virtual = DocumentTemplateFolderBinding(
            document_template=doc_poa, folder_template=folder_tpl, folder_node_id="", folder_node_path=""
        )
        result = SlotResolutionService().resolve_binding_path(virtual)
        assert result.skip is True
        assert result.path == ""

    def test_no_slot_declaration_uses_legacy(self, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate) -> None:
        binding = DocumentTemplateFolderBinding(
            document_template=doc_poa,
            folder_template=folder_tpl,
            folder_node_id="n_mail",
            folder_node_path="一审/4-邮件往来",
        )
        result = SlotResolutionService().resolve_binding_path(binding)
        assert result.path == "一审/4-邮件往来"


class TestIterEffectiveBindings:
    def test_slot_declared_template_without_binding_gets_virtual(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        doc_poa.folder_slot = slot_poa
        doc_poa.save(update_fields=["folder_slot", "updated_at"])
        bindings = SlotResolutionService().iter_effective_bindings(folder_tpl)
        assert len(bindings) == 1
        assert bindings[0].pk is None
        assert bindings[0].document_template == doc_poa

    def test_existing_binding_row_blocks_virtual(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        """已有绑定行（含停用）代表显式意图，不生成虚拟绑定"""
        doc_poa.folder_slot = slot_poa
        DocumentTemplateFolderBinding.objects.create(
            document_template=doc_poa,
            folder_template=folder_tpl,
            folder_node_id="n_poa",
            folder_node_path="一审/1-立案材料/3-委托材料",
            is_active=False,
        )
        bindings = SlotResolutionService().iter_effective_bindings(folder_tpl)
        assert len(bindings) == 0

    def test_saved_active_binding_kept(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        doc_poa.folder_slot = slot_poa
        DocumentTemplateFolderBinding.objects.create(
            document_template=doc_poa,
            folder_template=folder_tpl,
            folder_node_id="n_poa",
            folder_node_path="一审/1-立案材料/3-委托材料",
        )
        bindings = SlotResolutionService().iter_effective_bindings(folder_tpl)
        assert len(bindings) == 1
        assert bindings[0].pk is not None


class TestGetDocumentPlacementsSlot:
    def test_slot_declared_template_places_without_binding(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_contract: DocumentTemplate
    ) -> None:
        """核心承诺：声明槽位 + 骨架提供槽位 → 零绑定行也能落位"""
        doc_contract.folder_slot = slot_poa
        doc_contract.save(update_fields=["folder_slot", "updated_at"])
        contract = MagicMock()
        contract.case_type = "civil"
        contract.id = 1
        svc = FolderGenerationService()
        with patch.object(svc, "_generate_document_filename", return_value="poa.docx"):
            placements = svc.get_document_placements(contract, folder_tpl)
        assert len(placements) == 1
        assert placements[0].folder_path == "一审/1-立案材料/3-委托材料"

    def test_legacy_binding_without_slot_unchanged(self, folder_tpl: FolderTemplate, doc_contract: DocumentTemplate) -> None:
        DocumentTemplateFolderBinding.objects.create(
            document_template=doc_contract,
            folder_template=folder_tpl,
            folder_node_id="n_mail",
            folder_node_path="一审/4-邮件往来",
        )
        contract = MagicMock()
        contract.case_type = "civil"
        contract.id = 1
        svc = FolderGenerationService()
        with patch.object(svc, "_generate_document_filename", return_value="poa.docx"):
            placements = svc.get_document_placements(contract, folder_tpl)
        assert len(placements) == 1
        assert placements[0].folder_path == "一审/4-邮件往来"

    def test_slot_miss_without_binding_skips(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_contract: DocumentTemplate
    ) -> None:
        """骨架未提供该槽位且无绑定行 → 显式跳过（拒绝静默吞位）"""
        slot_missing = FolderSlot.objects.create(key="service_address", name="送达地址确认书")
        doc_contract.folder_slot = slot_missing
        doc_contract.save(update_fields=["folder_slot", "updated_at"])
        contract = MagicMock()
        contract.case_type = "civil"
        contract.id = 1
        svc = FolderGenerationService()
        with patch.object(svc, "_generate_document_filename", return_value="poa.docx"):
            placements = svc.get_document_placements(contract, folder_tpl)
        assert placements == []


class TestBackfillCommand:
    @pytest.fixture
    def legacy_world(self, db: Any) -> dict[str, Any]:
        """复刻存量形态：无 kind、无槽位，靠绑定表落位"""
        structure = {
            "children": [
                {
                    "id": "root",
                    "name": "一审",
                    "children": [
                        {
                            "id": "grp",
                            "name": "1-立案材料",
                            "children": [
                                {"id": "s1", "name": "1-起诉状和反诉答辩状", "children": []},
                                {"id": "s2", "name": "2-当事人身份证明", "children": []},
                                {"id": "s3", "name": "3-委托材料", "children": []},
                                {"id": "s4", "name": "6-送达地址确认书", "children": []},
                                {"id": "s5", "name": "4-其他答辩材料", "children": []},
                            ],
                        },
                    ],
                }
            ]
        }
        tpl = FolderTemplate.objects.create(name="回填骨架", template_type="case", case_types=["civil"], structure=structure)
        poa = DocumentTemplate.objects.create(
            name="授权委托书",
            template_type=DocumentTemplateType.CASE,
            case_sub_type=DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS,
            case_types=["all"],
            file_path="poa.docx",
        )
        foshan = DocumentTemplate.objects.create(
            name="佛山法院送达地址确认书",
            template_type=DocumentTemplateType.CASE,
            case_sub_type=DocumentCaseFileSubType.SERVICE_ADDRESS_MATERIALS,
            case_types=["all"],
            file_path="fs.docx",
        )
        DocumentTemplateFolderBinding.objects.create(
            document_template=poa, folder_template=tpl, folder_node_id="s3", folder_node_path="一审/1-立案材料/3-委托材料"
        )
        # 病理样本：佛山确认书一处绑到送达、两处绑到其他答辩材料
        DocumentTemplateFolderBinding.objects.create(
            document_template=foshan, folder_template=tpl, folder_node_id="s4", folder_node_path="p1"
        )
        DocumentTemplateFolderBinding.objects.create(
            document_template=foshan, folder_template=tpl, folder_node_id="s5", folder_node_path="p2"
        )
        return {"tpl": tpl, "poa": poa, "foshan": foshan}

    def _node(self, tpl: FolderTemplate, node_id: str) -> dict[str, Any]:
        found: list[dict[str, Any]] = []

        def walk(children: list[Any]) -> None:
            for child in children:
                if child.get("id") == node_id:
                    found.append(child)
                walk(child.get("children", []))

        walk((tpl.structure or {}).get("children", []))
        return found[0]

    def test_backfill_assigns_kinds_and_slots(self, legacy_world: dict[str, Any]) -> None:
        call_command("backfill_folder_slots", verbosity=0)
        tpl = FolderTemplate.objects.get(pk=legacy_world["tpl"].pk)
        assert self._node(tpl, "s3")["kind"] == "power_of_attorney"
        assert self._node(tpl, "s2")["kind"] == "identity_proof"
        assert self._node(tpl, "s1")["kind"] == "complaint"
        assert self._node(tpl, "s4")["kind"] == "service_address"
        assert self._node(tpl, "s5")["kind"] == "other_defense"

        poa = DocumentTemplate.objects.get(pk=legacy_world["poa"].pk)
        assert poa.folder_slot is not None
        assert poa.folder_slot.key == "power_of_attorney"

        # 病理样本修正：名称子串决胜，选 service_address 而非多数派的 other_defense
        foshan = DocumentTemplate.objects.get(pk=legacy_world["foshan"].pk)
        assert foshan.folder_slot is not None
        assert foshan.folder_slot.key == "service_address"

    def test_dry_run_changes_nothing(self, legacy_world: dict[str, Any]) -> None:
        call_command("backfill_folder_slots", "--dry-run", verbosity=0)
        tpl = legacy_world["tpl"]
        assert "kind" not in self._node(tpl, "s3")
        assert FolderSlot.objects.count() == 0
        poa = DocumentTemplate.objects.get(pk=legacy_world["poa"].pk)
        assert poa.folder_slot is None

    def test_idempotent(self, legacy_world: dict[str, Any]) -> None:
        call_command("backfill_folder_slots", verbosity=0)
        tpl = FolderTemplate.objects.get(pk=legacy_world["tpl"].pk)
        self._node(tpl, "s3")["name"] = "3-授权与委托文件"
        tpl.save(update_fields=["structure", "updated_at"])
        call_command("backfill_folder_slots", verbosity=0)
        # 已有 kind 不被重置；名称变化不影响
        assert self._node(tpl, "s3")["kind"] == "power_of_attorney"
        assert FolderSlot.objects.filter(key="power_of_attorney").count() == 1


class TestFolderSlotStr:
    def test_str_contains_short_category(self, slot_poa: FolderSlot) -> None:
        assert str(slot_poa) == "委托材料 (power_of_attorney) · 通用"

    def test_short_category_mapping(self, db: Any) -> None:
        slot = FolderSlot.objects.create(key="complaint", name="起诉状", category="filing")
        assert slot.short_category == "立案"
        assert "· 立案" in str(slot)


class TestValidateSlotKinds:
    def _make_world(self, db: Any) -> None:
        FolderSlot.objects.create(key="power_of_attorney", name="委托材料", category="general")

    def test_valid_kind_passes(self, db: Any) -> None:
        self._make_world(db)
        svc = FolderTemplateAdminService()
        structure = {"children": [{"name": "3-委托材料", "kind": "power_of_attorney", "children": []}]}
        assert svc.validate_slot_kinds(structure) == []

    def test_unknown_kind_reported_with_node_name(self, db: Any) -> None:
        self._make_world(db)
        svc = FolderTemplateAdminService()
        structure = {
            "children": [
                {"name": "3-委托材料", "kind": "power_of_attorney", "children": []},
                {"name": "X-错别字节点", "kind": "power_of_atterney", "children": []},
            ]
        }
        bad = svc.validate_slot_kinds(structure)
        assert bad == ["X-错别字节点 → power_of_atterney"]

    def test_structure_preview_renders_kind_badge(self, db: Any) -> None:
        self._make_world(db)
        svc = FolderTemplateAdminService()
        structure = {"children": [{"name": "3-委托材料", "kind": "power_of_attorney", "children": []}]}
        html = svc.render_structure_preview(structure)
        assert "⌘" in str(html) and "委托材料" in str(html)


class TestLegacyBindingRetirement:
    """旧绑定通道退役：inline 仅在有存量行时出现；绑定 admin 禁止新增"""

    def test_inline_hidden_without_bindings(self, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate) -> None:
        from django.contrib.admin.sites import AdminSite

        from apps.documents.admin.document_template_admin import (
            DocumentTemplateAdmin,
            DocumentTemplateFolderBindingInline,
        )

        admin_obj = DocumentTemplateAdmin(DocumentTemplate, AdminSite())
        assert DocumentTemplateFolderBindingInline not in admin_obj.get_inlines(MagicMock(), doc_poa)
        DocumentTemplateFolderBinding.objects.create(
            document_template=doc_poa, folder_template=folder_tpl, folder_node_id="n_poa", folder_node_path="p"
        )
        assert DocumentTemplateFolderBindingInline in admin_obj.get_inlines(MagicMock(), doc_poa)

    def test_binding_admin_forbids_add(self, db: Any) -> None:
        from django.contrib.admin.sites import AdminSite

        from apps.documents.admin.folder_binding_admin import DocumentTemplateFolderBindingAdmin

        admin_obj = DocumentTemplateFolderBindingAdmin(DocumentTemplateFolderBinding, AdminSite())
        assert admin_obj.has_add_permission(MagicMock()) is False

    def test_effect_display_reports_slot_vs_legacy(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        from django.contrib.admin.sites import AdminSite

        from apps.documents.admin.folder_binding_admin import DocumentTemplateFolderBindingAdmin

        admin_obj = DocumentTemplateFolderBindingAdmin(DocumentTemplateFolderBinding, AdminSite())
        doc_poa.folder_slot = slot_poa
        doc_poa.save(update_fields=["folder_slot", "updated_at"])
        binding = DocumentTemplateFolderBinding.objects.create(
            document_template=doc_poa, folder_template=folder_tpl, folder_node_id="n_poa", folder_node_path="p"
        )
        assert "已被槽位取代" in str(admin_obj.effect_display(binding))
        # 换成骨架未提供的槽位 → 兜底生效
        missing = FolderSlot.objects.create(key="service_address", name="送达地址确认书")
        doc_poa.folder_slot = missing
        doc_poa.save(update_fields=["folder_slot", "updated_at"])
        binding.refresh_from_db()
        assert "兜底生效" in str(admin_obj.effect_display(binding))


class TestDuplicateTemplateCopiesBindings:
    def test_duplicate_carries_bindings(
        self, slot_poa: FolderSlot, folder_tpl: FolderTemplate, doc_poa: DocumentTemplate
    ) -> None:
        DocumentTemplateFolderBinding.objects.create(
            document_template=doc_poa,
            folder_template=folder_tpl,
            folder_node_id="n_poa",
            folder_node_path="一审/1-立案材料/3-委托材料",
        )
        new_tpl = FolderTemplateAdminService().duplicate_template(folder_tpl)
        assert new_tpl.name.startswith("测试骨架 (副本")
        assert new_tpl.document_bindings.filter(is_active=True).count() == 1
        copied = new_tpl.document_bindings.get()
        assert copied.folder_node_id == "n_poa"
        assert copied.folder_node_path == "一审/1-立案材料/3-委托材料"
