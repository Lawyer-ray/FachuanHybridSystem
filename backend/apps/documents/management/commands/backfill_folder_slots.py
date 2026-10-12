"""
槽位体系回填命令

一次性把存量数据接入槽位体系（幂等，可重复执行）：
1. 种子槽位词表（FolderSlot，update_or_create，不改既有名称）
2. 回填文件夹模板 structure 节点的 kind（按「去序号名称 → 槽位名」匹配，不覆盖已有 kind）
3. 回填文书模板的 folder_slot（按绑定节点上的 kind 汇总，名称子串决胜）

用法：
    python manage.py backfill_folder_slots            # 实际执行
    python manage.py backfill_folder_slots --dry-run  # 只打印计划
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.documents.models import DocumentTemplate, DocumentTemplateFolderBinding, FolderSlot, FolderTemplate

# 槽位词表初版（2026-10-12 设计稿）：按开发库「去序号名称」归组推导，命名可在 admin 中随时调整
SEED_SLOTS: list[dict[str, str]] = [
    {
        "key": "identity_proof",
        "name": "当事人身份证明",
        "description": "主体资格文件：身份证、营业执照、法定代表人身份证明书",
        "category": "general",
    },
    {
        "key": "power_of_attorney",
        "name": "委托材料",
        "description": "授权委托书、所函等委托手续",
        "category": "general",
    },
    {"key": "evidence_list", "name": "证据目录", "description": "", "category": "filing"},
    {"key": "evidence_materials", "name": "证据材料", "description": "", "category": "filing"},
    {
        "key": "service_address",
        "name": "送达地址确认书",
        "description": "含广州/佛山/东莞等地法院变体",
        "category": "filing",
    },
    {"key": "refund_account", "name": "退费账户确认书", "description": "领退转款账户", "category": "filing"},
    {"key": "preservation", "name": "保全申请书及保函", "description": "", "category": "filing"},
    {"key": "complaint", "name": "起诉状", "description": "含反诉答辩状", "category": "filing"},
    {"key": "defense", "name": "答辩状", "description": "含反诉状", "category": "defense"},
    {"key": "appeal", "name": "上诉状", "description": "", "category": "appeal"},
    {"key": "execution_request", "name": "强制执行申请书", "description": "", "category": "filing"},
    {"key": "reconsideration", "name": "复议申请书", "description": "行政复议程序", "category": "filing"},
    {
        "key": "restrictive_measures",
        "name": "限制性措施",
        "description": "限高 / 失信 / 限制出境 / 媒体公布",
        "category": "filing",
    },
    {"key": "enforcement_basis", "name": "执行依据及生效证明", "description": "", "category": "filing"},
    {"key": "settlement", "name": "和解(调解)协议", "description": "", "category": "closing"},
    {"key": "withdrawal", "name": "撤诉申请书", "description": "", "category": "closing"},
    {"key": "withdraw_reconsideration", "name": "撤回行政复议申请书", "description": "", "category": "closing"},
    {"key": "unsealing", "name": "解除查封申请书", "description": "", "category": "closing"},
    {"key": "refund_pending", "name": "申请退费(待申请)", "description": "", "category": "closing"},
    {"key": "correspondence", "name": "邮件往来", "description": "", "category": "general"},
    {"key": "other_filing", "name": "其他立案材料", "description": "", "category": "filing"},
    {"key": "other_defense", "name": "其他答辩材料", "description": "", "category": "defense"},
    {"key": "question_list", "name": "问题清单", "description": "庭审准备", "category": "trial_prep"},
    {"key": "trial_outline", "name": "庭审提纲", "description": "庭审准备", "category": "trial_prep"},
    {"key": "cross_exam", "name": "质证意见", "description": "庭审准备", "category": "trial_prep"},
    {"key": "timeline", "name": "时间轴大事记", "description": "庭审准备", "category": "trial_prep"},
    {"key": "agent_opinion", "name": "代理意见", "description": "庭审准备", "category": "trial_prep"},
    {"key": "other_trial", "name": "其他材料", "description": "庭审准备", "category": "trial_prep"},
    {"key": "other_closing", "name": "其他结案文书", "description": "", "category": "closing"},
    {"key": "contract", "name": "合同", "description": "合同文件夹用", "category": "contract"},
    {"key": "supplementary", "name": "补充协议", "description": "合同文件夹用", "category": "contract"},
]

_SEQ_PREFIX_RE = re.compile(r"^\d+[-—.]?\s*")


@dataclass
class SeedStats:
    created: int = 0
    updated: int = 0


@dataclass
class KindStats:
    templates_touched: int = 0
    tagged: int = 0
    unmatched_names: Counter[str] = field(default_factory=Counter)


@dataclass
class DocStats:
    assigned: int = 0
    skipped: int = 0
    assignments: list[tuple[str, str]] = field(default_factory=list)


def strip_sequence(name: str) -> str:
    """去掉节点名称的开头序号：'3-委托材料' → '委托材料'"""
    return _SEQ_PREFIX_RE.sub("", str(name or "").strip())


class Command(BaseCommand):
    help: str = "回填槽位体系：种子词表 + 节点 kind + 文书模板 folder_slot（幂等）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true", help="只打印计划，不修改数据")

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options.get("dry_run"))
        self.stdout.write(self.style.SUCCESS("=== 槽位体系回填 ===\n"))

        # 词表按名称降序，前缀匹配时长的优先（避免「起诉状」抢走「起诉状和反诉答辩状」类误配）
        name_to_slot = {s["name"]: s["key"] for s in SEED_SLOTS}
        sorted_names = sorted(name_to_slot, key=len, reverse=True)

        with transaction.atomic():
            slot_stats = self._seed_slots(dry_run=dry_run)
            kind_stats = self._backfill_kinds(name_to_slot=name_to_slot, sorted_names=sorted_names, dry_run=dry_run)
            doc_stats = self._backfill_document_slots(dry_run=dry_run)

        self._print_summary(slot_stats, kind_stats, doc_stats, dry_run=dry_run)

    # ------------------------------------------------------------------
    # 1. 种子词表
    # ------------------------------------------------------------------
    def _seed_slots(self, *, dry_run: bool) -> SeedStats:
        stats = SeedStats()
        for seed in SEED_SLOTS:
            if dry_run:
                if not FolderSlot.objects.filter(key=seed["key"]).exists():
                    stats.created += 1
                continue
            _, was_created = FolderSlot.objects.update_or_create(
                key=seed["key"],
                defaults={"name": seed["name"], "description": seed["description"], "category": seed["category"]},
            )
            if was_created:
                stats.created += 1
            else:
                stats.updated += 1
        return stats

    # ------------------------------------------------------------------
    # 2. 节点 kind 回填
    # ------------------------------------------------------------------
    def _backfill_kinds(self, *, name_to_slot: dict[str, str], sorted_names: list[str], dry_run: bool) -> KindStats:
        def match_slot(node_name: str) -> str | None:
            normalized = strip_sequence(node_name)
            if not normalized:
                return None
            if normalized in name_to_slot:
                return name_to_slot[normalized]
            # 前缀匹配（'起诉状' ← '起诉状和反诉答辩状'、'答辩状' ← '答辩状(反诉状)'）
            for slot_name in sorted_names:
                if normalized.startswith(slot_name):
                    return name_to_slot[slot_name]
            return None

        def walk(children: list[Any]) -> int:
            tagged = 0
            for child in children:
                if not isinstance(child, dict):
                    continue
                if not child.get("kind"):
                    slot_key = match_slot(child.get("name", ""))
                    if slot_key:
                        child["kind"] = slot_key
                        tagged += 1
                tagged += walk(child.get("children", []))
            return tagged

        stats = KindStats()
        for template in FolderTemplate.objects.all():
            structure = template.structure
            if not structure or not structure.get("children"):
                continue

            def collect_unmatched(children: list[Any], counter: Counter[str]) -> None:
                for child in children:
                    if not isinstance(child, dict):
                        continue
                    if not child.get("kind") and not match_slot(child.get("name", "")):
                        counter[strip_sequence(child.get("name", ""))] += 1
                    collect_unmatched(child.get("children", []), counter)

            collect_unmatched(structure.get("children", []), stats.unmatched_names)
            tagged = walk(structure.get("children", []))
            if tagged:
                if not dry_run:
                    template.save(update_fields=["structure", "updated_at"])
                stats.templates_touched += 1
                stats.tagged += tagged
        return stats

    # ------------------------------------------------------------------
    # 3. 文书模板 folder_slot 回填
    # ------------------------------------------------------------------
    def _backfill_document_slots(self, *, dry_run: bool) -> DocStats:
        def find_kind_by_node_id(folder_template: FolderTemplate, node_id: str) -> str | None:
            found: list[str] = []

            def walk(children: list[Any]) -> None:
                for child in children:
                    if not isinstance(child, dict):
                        continue
                    if child.get("id") == node_id and child.get("kind"):
                        found.append(str(child["kind"]))
                    walk(child.get("children", []))

            walk((folder_template.structure or {}).get("children", []))
            return found[0] if found else None

        stats = DocStats()
        bindings = (
            DocumentTemplateFolderBinding.objects.filter(is_active=True)
            .select_related("document_template", "folder_template")
            .order_by("document_template_id")
        )
        candidates: dict[int, Counter[str]] = {}
        for binding in bindings:
            kind = find_kind_by_node_id(binding.folder_template, binding.folder_node_id)
            if kind:
                candidates.setdefault(binding.document_template_id, Counter())[kind] += 1

        for template in DocumentTemplate.objects.filter(folder_slot__isnull=True):
            counter = candidates.get(template.id)
            if not counter:
                continue
            chosen = self._choose_slot(counter, template.name)
            slot = FolderSlot.objects.filter(key=chosen).first() if chosen else None
            if slot is None:
                stats.skipped += 1
                continue
            stats.assignments.append((template.name, slot.key))
            if not dry_run:
                template.folder_slot = slot
                template.save(update_fields=["folder_slot", "updated_at"])
            stats.assigned += 1
        return stats

    def _choose_slot(self, counter: Counter[str], template_name: str) -> str | None:
        """从绑定节点的 kind 分布中选槽位：名称子串决胜（修病理样本：佛山确认书被塞进其他答辩材料）"""
        if len(counter) == 1:
            return next(iter(counter))
        name_by_key = {s["key"]: s["name"] for s in SEED_SLOTS}
        for key, _count in counter.most_common():
            slot_name = name_by_key.get(key, "")
            if slot_name and slot_name in template_name:
                return key
        top = counter.most_common()
        if len(top) >= 2 and top[0][1] > top[1][1]:
            return top[0][0]
        return None

    # ------------------------------------------------------------------
    def _print_summary(
        self,
        slot_stats: SeedStats,
        kind_stats: KindStats,
        doc_stats: DocStats,
        *,
        dry_run: bool,
    ) -> None:
        mode = "（dry-run，未实际修改）" if dry_run else ""
        self.stdout.write(f"\n[1] 槽位词表{mode}：新建 {slot_stats.created}，更新 {slot_stats.updated}")
        self.stdout.write(
            f"[2] 节点 kind{mode}：{kind_stats.templates_touched} 个模板共标记 {kind_stats.tagged} 个节点"
        )
        if kind_stats.unmatched_names:
            detail = "、".join(f"{name}×{count}" for name, count in kind_stats.unmatched_names.most_common(10))
            self.stdout.write(self.style.WARNING(f"    未匹配节点（保留无 kind）：{detail}"))
        self.stdout.write(f"[3] 文书落位声明{mode}：赋值 {doc_stats.assigned}，跳过 {doc_stats.skipped}")
        for name, key in doc_stats.assignments:
            self.stdout.write(f"    {name} → {key}")
        self.stdout.write(self.style.SUCCESS("\n完成。"))
