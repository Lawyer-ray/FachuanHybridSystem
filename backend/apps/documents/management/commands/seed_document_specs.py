"""
文书起草规格种子命令

幂等（update_or_create）：反复执行只会把这几条规格与槽位词表校正到最新口径。

为什么骨架按 file_path 匹配而不是写死 id：模板库在开发库/生产库/新环境里 id 各不相同，
写死 id 的种子在别的库上要么静默错配到别的文书，要么直接炸。file_path 是模板的业务标识。

缺骨架就整条命令失败（先预检、后写入）：只种一半的规格比不种更危险——
律师会以为「这个文书可以一句话起草」，直到出稿时才发现骨架不在。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.documents.models import DocumentSpec, DocumentTemplate, FolderSlot
from apps.documents.models.choices import FolderSlotCategory
from apps.documents.models.document_spec import DraftFamily, SlotSource

COMPLAINT_TEMPLATE_PATH = "2-案件材料/1-起诉材料/1-起诉状和反诉答辩状/1-起诉状.docx"
DEFENSE_TEMPLATE_PATH = "2-案件材料/2-答辩材料/1-答辩状和反诉状/1-答辩状.docx"

SEED_SLOTS: list[dict[str, Any]] = [
    {
        "key": "jurisdiction_objection",
        "name": "管辖权异议",
        # 异议申请在立案阶段提交、与「其他立案材料」并列，归 filing 而不是通用
        "category": FolderSlotCategory.FILING,
    },
]

#: 规格字段的基线值：种子只覆盖它关心的那几项，重跑才能把手工改乱的字段校回来
_SPEC_DEFAULTS: dict[str, Any] = {
    "family": DraftFamily.LITIGATION,
    "title_override": "",
    "folder_slot": "",
    "party_label": "",
    "claim_heading": "",
    "claim_source": SlotSource.LLM,
    "claim_text": "",
    "claim_slot_key": "",
    "facts_heading": "",
    "facts_source": SlotSource.LLM,
    "facts_slot_key": "",
    "extra_slots": [],
    "ai_brief": "",
    "is_active": True,
}

#: 骨架 docx 若尚未登记为 `DocumentTemplate`，由本命令补登记（幂等）。
#:
#: 为什么允许命令自己登记：起草的入口是「律师说一句话」，而不是「先去 Admin 里加一条模板」。
#: 答辩状这类文书一直只有 docx 文件、没有模板记录，生成链路只能靠代码里写死路径拿到它
#: （见 `litigation_generation_service._defense_template_path`）——那条硬编码路径正是
#: 「模板库在哪个库、id 是多少」这件事无法被 Admin 管起来的原因。
#:
#: 只补不覆盖：记录已存在时一个字段都不改（管理员在 Admin 里的调整优先级最高）。
SKELETON_TEMPLATES: list[dict[str, Any]] = [
    {
        "file_path": DEFENSE_TEMPLATE_PATH,
        "name": "答辩状",
        "template_type": "case",
        "case_sub_type": "pleading_materials",
        # 适用案件类型留空 = 不额外过滤；具体范围由管理员在 Admin 按所内实际调整。
        "case_types": [],
    },
]


SEED_SPECS: list[dict[str, Any]] = [
    {
        "doc_type": "complaint",
        "display_name": "起诉状",
        "family": DraftFamily.LITIGATION,
        "skeleton_file_path": COMPLAINT_TEMPLATE_PATH,
        "folder_slot": "complaint",
        "party_label": "原告",
        "claim_source": SlotSource.LLM,
        "facts_source": SlotSource.LLM,
        # 诉请结构是最容易被模型漏掉的一项：真机 3 次起草里「解除合同」出现 3 次、
        # 「履约保证金」只出现 1 次，而保证金恰恰是那类案子的主战场。写在这里而不是
        # 塞进 prompt：一所之内改口径不该动代码。
        "ai_brief": (
            "诉讼请求逐项写全，每项都要可执行：①欠款本金按项目分列并给出合计；"
            "②逾期违约金/滞纳金写清计算基数、比率与起止时间；③合同约定或法定解除的，写明解除哪份合同；"
            "④有履约保证金/押金的，写明不予退还或抵扣（金额以合同原文为准）；"
            "⑤需要返还土地、房屋、设备的，写明返还标的与范围；⑥维权费用（律师费、保全费、担保费）"
            "写明以实际发生为准。事实与理由按时间顺序：合同签订与关键条款 → 我方已履行 → 对方违约事实"
            "（欠款项目、期间、到期日）→ 催告与对方反应。只用材料里能读到的事实，"
            "不得补写材料里没有的金额、日期、条款号。"
        ),
    },
    {
        "doc_type": "defense",
        "display_name": "答辩状",
        "family": DraftFamily.LITIGATION,
        "skeleton_file_path": DEFENSE_TEMPLATE_PATH,
        "folder_slot": "defense",
        "party_label": "被告",
        # 答辩请求是律所验证过的固定表述：不交给模型改写
        "claim_source": SlotSource.FIXED,
        "claim_text": "请求依法驳回原告的全部诉讼请求。",
        "facts_source": SlotSource.LLM,
        "ai_brief": (
            "答辩理由按争点组织：先否认或说明原告主张不能成立的事实，再逐个争点回应"
            "（合同效力、履行情况、金额计算、违约责任、时效与管辖），最后落到请求驳回全部诉请。"
            "只用材料里能读到的事实，不得补写材料里没有的金额、日期、条款号。"
        ),
    },
    {
        # 复用起诉状骨架（零新 docx）：两族实测同构，新文书只加一行规格
        "doc_type": "jurisdiction_objection",
        "display_name": "管辖权异议申请书",
        "family": DraftFamily.LITIGATION,
        "skeleton_file_path": COMPLAINT_TEMPLATE_PATH,
        "title_override": "管辖权异议申请书",
        "folder_slot": "jurisdiction_objection",
        "party_label": "异议人",
        "claim_heading": "异议请求：",
        "claim_source": SlotSource.LLM,
        "facts_heading": "事实与理由：",
        "facts_source": SlotSource.LLM,
        "extra_slots": [{"key": "原受理法院", "label": "原受理法院", "source": SlotSource.SLOT.value}],
        "ai_brief": (
            "针对受诉法院无管辖权（地域/级别/协议管辖）陈述异议理由，只陈述管辖问题、不作实体抗辩，"
            "引用民事诉讼法相应条文。"
        ),
    },
]


class Command(BaseCommand):
    help: str = "种子文书起草规格（DocumentSpec）与管辖权异议槽位（幂等）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--register-missing-skeletons",
            action="store_true",
            help="把 SKELETON_TEMPLATES 里列出、但还没登记成模板的骨架 docx 补登记（默认关）",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(self.style.SUCCESS("=== 文书起草规格种子 ===\n"))
        if options.get("register_missing_skeletons"):
            self._ensure_skeleton_templates()
        templates = self._resolve_templates()
        with transaction.atomic():
            slot_stats = self._seed_slots()
            spec_stats = self._seed_specs(templates)
        self.stdout.write(f"[1] 槽位词表：新建 {slot_stats[0]}，更新 {slot_stats[1]}")
        self.stdout.write(f"[2] 起草规格：新建 {spec_stats[0]}，更新 {spec_stats[1]}")
        self.stdout.write(self.style.SUCCESS("\n完成。"))

    def _ensure_skeleton_templates(self) -> int:
        """把只有 docx 文件、还没登记成模板的骨架补登记进去。返回新建条数。

        只在显式带 `--register-missing-skeletons` 时执行（默认关）。原因是本命令的默认
        契约更重要：**骨架缺任何一份就整体失败、一个字段都不写**——半套种子会让「哪几个
        文书能起草」变成一个要靠翻库才知道的隐性状态。

        另外必须先确认文件真在盘上：登记一条指向不存在文件的模板，比没有记录更糟
        （Admin 里看着是好的，生成时才炸）。
        """
        created = 0
        for seed in SKELETON_TEMPLATES:
            probe = DocumentTemplate(file_path=seed["file_path"])
            location = probe.get_file_location()
            if not location or not Path(location).is_file():
                self.stdout.write(
                    self.style.WARNING(f"  - 跳过补登记（文件不在盘上）：{seed['name']}（{seed['file_path']}）")
                )
                continue
            defaults = {key: value for key, value in seed.items() if key != "file_path"}
            _, was_created = DocumentTemplate.objects.get_or_create(file_path=seed["file_path"], defaults=defaults)
            if was_created:
                self.stdout.write(f"  + 补登记骨架模板：{seed['name']}（{seed['file_path']}）")
                created += 1
        return created

    def _resolve_templates(self) -> dict[str, Any]:
        """按 file_path 预检全部骨架；缺任何一个就整条命令失败，并说清缺哪个文件。"""
        templates: dict[str, Any] = {}
        missing: list[str] = []
        for path in dict.fromkeys(str(spec["skeleton_file_path"]) for spec in SEED_SPECS):
            template = DocumentTemplate.objects.filter(file_path=path).first()
            if template is None:
                missing.append(path)
                continue
            templates[path] = template
        if missing:
            detail = "\n".join(f"  - {path}" for path in missing)
            raise CommandError(f"缺少骨架模板（先在「文书模板」里登记这些 docx，再重跑本命令）：\n{detail}")
        return templates

    def _seed_slots(self) -> tuple[int, int]:
        created = updated = 0
        for seed in SEED_SLOTS:
            _, was_created = FolderSlot.objects.update_or_create(
                key=seed["key"],
                defaults={"name": seed["name"], "category": seed["category"]},
            )
            created += int(was_created)
            updated += int(not was_created)
        return created, updated

    def _seed_specs(self, templates: dict[str, Any]) -> tuple[int, int]:
        created = updated = 0
        for seed in SEED_SPECS:
            defaults = _SPEC_DEFAULTS | {key: value for key, value in seed.items() if key != "doc_type"}
            defaults["skeleton_template"] = templates[str(defaults.pop("skeleton_file_path"))]
            _, was_created = DocumentSpec.objects.update_or_create(doc_type=seed["doc_type"], defaults=defaults)
            created += int(was_created)
            updated += int(not was_created)
        return created, updated
