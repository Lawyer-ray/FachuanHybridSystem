"""
槽位解析服务

文书落位体系的核心解析器：文书模板声明 FolderSlot（落位槽位），
文件夹模板的 structure 节点通过 kind 标记自己提供哪个槽位，
本服务在生成时刻把两者接起来，现场派生落位路径（不落库）。

解析优先级（绞杀者模式，向后兼容）：
1. 模板声明了槽位且骨架提供该槽位 → 派生路径（结构改名/调序自动跟随）
2. 模板声明了槽位但骨架未提供 → 回退旧绑定路径（存量行为不动），记日志
3. 模板未声明槽位 → 沿用旧绑定路径

另提供 iter_effective_bindings：已保存绑定 + 「已声明槽位但无绑定行」的虚拟绑定，
使新增文件夹模板后无需补建任何绑定行。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.documents.models import DocumentTemplate, DocumentTemplateFolderBinding, FolderTemplate

logger = logging.getLogger(__name__)

RESOLVED_BY_SLOT = "slot"
RESOLVED_BY_LEGACY = "legacy"


@dataclass(frozen=True)
class SlotPathResolution:
    """单次落位路径解析结果"""

    path: str
    resolved_by: str
    skip: bool = False


class SlotResolutionService:
    """槽位 → 落位路径 解析器（纯读，不落库）"""

    def find_slot_paths(self, folder_template: FolderTemplate, slot_key: str) -> list[list[str]]:
        """
        在文件夹模板 structure 树中查找 kind == slot_key 的节点。

        Returns:
            匹配节点的路径段列表（与绑定 folder_node_path 同构：自 structure 顶层子节点起），
            如 [["一审", "1-立案材料", "3-委托材料"]]；未命中返回空列表。
        """
        structure = folder_template.structure or {}
        return self._walk(structure.get("children", []), slot_key, [])

    def _walk(self, children: list[Any], slot_key: str, current_path: list[str]) -> list[list[str]]:
        results: list[list[str]] = []
        for child in children:
            if not isinstance(child, dict):
                continue
            path = current_path + [str(child.get("name", ""))]
            if child.get("kind") == slot_key:
                results.append(path)
            results.extend(self._walk(child.get("children", []), slot_key, path))
        return results

    def resolve_binding_path(self, binding: DocumentTemplateFolderBinding) -> SlotPathResolution:
        """
        解析一条绑定（或虚拟绑定）的落位路径。

        - 声明槽位且命中：返回派生路径
        - 声明槽位未命中：存量绑定回退旧路径（记日志）；虚拟绑定返回 skip=True（拒绝静默吞位）
        - 未声明槽位：沿用旧路径
        """
        template = binding.document_template
        slot = getattr(template, "folder_slot", None)
        legacy_path = binding.folder_node_path or ""

        if slot is None or not slot.is_active:
            return SlotPathResolution(path=legacy_path, resolved_by=RESOLVED_BY_LEGACY)

        paths = self.find_slot_paths(binding.folder_template, slot.key)
        if paths:
            if len(paths) > 1:
                logger.debug(
                    "槽位多节点命中，取第一个: slot=%s, folder=%s, 命中数=%d",
                    slot.key,
                    binding.folder_template_id,
                    len(paths),
                    extra={"slot": slot.key, "folder_template_id": binding.folder_template_id, "hits": len(paths)},
                )
            return SlotPathResolution(path="/".join(paths[0]), resolved_by=RESOLVED_BY_SLOT)

        if binding.pk:
            logger.info(
                "槽位未命中，回退旧绑定路径: template=%s, slot=%s, folder=%s",
                template.name,
                slot.key,
                binding.folder_template.name,
                extra={
                    "template_name": template.name,
                    "slot": slot.key,
                    "folder_template_id": binding.folder_template_id,
                },
            )
            return SlotPathResolution(path=legacy_path, resolved_by=RESOLVED_BY_LEGACY)

        logger.warning(
            "槽位未命中，跳过落位（虚拟绑定，无旧路径可回退）: template=%s, slot=%s, folder=%s",
            template.name,
            slot.key,
            binding.folder_template.name,
            extra={
                "template_name": template.name,
                "slot": slot.key,
                "folder_template_id": binding.folder_template_id,
            },
        )
        return SlotPathResolution(path="", resolved_by=RESOLVED_BY_LEGACY, skip=True)

    def iter_effective_bindings(self, folder_template: FolderTemplate) -> list[DocumentTemplateFolderBinding]:
        """
        生效绑定全集 = 已启用的存量绑定 + 「已声明槽位但与该骨架无任何绑定行」的虚拟绑定。

        虚拟绑定不落库，仅用于生成期迭代；其存在使新增文件夹模板后零绑定操作成为可能。
        若模板与该骨架存在任何绑定行（含停用），不生成虚拟绑定——停用行代表用户的显式意图。
        """
        bindings = list(
            DocumentTemplateFolderBinding.objects.filter(
                folder_template=folder_template,
                is_active=True,
            ).select_related("document_template__folder_slot", "folder_template")
        )
        covered = {b.document_template_id for b in bindings}
        slot_templates = (
            DocumentTemplate.objects.filter(is_active=True, folder_slot__is_active=True)
            .select_related("folder_slot")
            .exclude(id__in=covered)
            .exclude(folder_bindings__folder_template=folder_template)
        )
        virtual: list[DocumentTemplateFolderBinding] = []
        for template in slot_templates:
            virtual.append(
                DocumentTemplateFolderBinding(
                    document_template=template,
                    folder_template=folder_template,
                    folder_node_id="",
                    folder_node_path="",
                )
            )
        if virtual:
            logger.info(
                "槽位虚拟绑定参与生成: folder=%s, 虚拟绑定数=%d",
                folder_template.name,
                len(virtual),
                extra={"folder_template_id": folder_template.id, "virtual_count": len(virtual)},
            )
        return bindings + virtual

    def slot_exists_in(self, folder_template: FolderTemplate, slot_key: str) -> bool:
        """骨架是否提供指定槽位（admin 落位预览等场景使用）"""
        return bool(self.find_slot_paths(folder_template, slot_key))
