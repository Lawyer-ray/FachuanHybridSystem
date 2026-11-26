"""
法律文书生成系统 - 文书起草规格模型

一句话起草的「类型 → 骨架」映射表：新增一种文书只插一行数据，不新增 docx。
骨架族（family）是实测确认过的那条脊柱（标题 → 当事人 → 〔请求事项〕→ 内容 →
〔事实与理由〕→ 内容 → 此致 → 法院 → 落款）；规格只决定「哪几个槽由谁填」，
排版动作不存在——AI 一旦能改结构，复核成本就超过它省下的时间。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django_lifecycle import LifecycleModel


class DraftFamily(models.TextChoices):
    """骨架族：同一族共用一份 docx 脊柱"""

    LITIGATION = "litigation_v1", "诉讼/申请文书骨架"
    FORM = "form_v1", "法院表单/确认书"


class SlotSource(models.TextChoices):
    """单个槽的素材来源"""

    FIXED = "fixed", "固定文案"
    SLOT = "slot", "取事实槽"
    LLM = "llm", "模型撰写"


class DocumentSpec(LifecycleModel):
    """
    文书起草规格

    doc_type 是律师嘴里的那个词的唯一拼写（也是 REST/MCP 的入参）；
    一行规格 = 一种可一句话起草的文书，缺规格就明确拒绝生成，绝不猜格式。
    """

    id: int

    doc_type: Any = models.SlugField(
        max_length=64,
        unique=True,
        verbose_name="文书类型",
        help_text="小写英文与下划线（如 jurisdiction_objection）；对外接口按它匹配，一经引用不可修改",
    )
    display_name: Any = models.CharField(max_length=100, verbose_name="文书名称")
    family: Any = models.CharField(
        max_length=32,
        choices=DraftFamily.choices,
        default=DraftFamily.LITIGATION,
        verbose_name="骨架族",
        help_text="决定套哪条脊柱；未显式声明目标占位符时，解析器按族的标准节名认领",
    )
    skeleton_template: Any = models.ForeignKey(
        "documents.DocumentTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="document_specs",
        verbose_name="骨架模板",
        help_text="实际渲染用的 docx；多种文书可复用同一份骨架（如管辖权异议复用起诉状）",
    )
    title_override: Any = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="标题覆盖",
        help_text="留空则沿用骨架标题；共用骨架的文书必须在这里改标题，否则出稿仍叫「民事起诉状」",
    )
    folder_slot: Any = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="落位槽位",
        help_text="FolderSlot.key；成稿落到文件夹模板中提供该槽位的节点，留空表示不自动落位",
    )
    party_label: Any = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="当事人称谓",
        help_text="我方在本文书里的称谓（原告/被告/异议人），供起草提示词与前端展示",
    )
    claim_heading: Any = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="请求段小标题",
        help_text="如「异议请求：」；留空沿用骨架里写死的小标题",
    )
    claim_source: Any = models.CharField(
        max_length=16,
        choices=SlotSource.choices,
        default=SlotSource.LLM,
        verbose_name="请求段来源",
    )
    claim_text: Any = models.TextField(
        blank=True,
        default="",
        verbose_name="请求段固定文案",
        help_text="仅 claim_source=fixed 时使用；律所已经验证过的固定表述不交给模型",
    )
    claim_slot_key: Any = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="请求段槽位键",
        help_text="source=slot 时从 facts 取同名键；非空时也指定请求段落到骨架的哪个占位符",
    )
    facts_heading: Any = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="事实段小标题",
    )
    facts_source: Any = models.CharField(
        max_length=16,
        choices=SlotSource.choices,
        default=SlotSource.LLM,
        verbose_name="事实段来源",
    )
    facts_slot_key: Any = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="事实段槽位键",
        help_text="source=slot 时从 facts 取同名键；非空时也指定事实段落到骨架的哪个占位符",
    )
    extra_slots: Any = models.JSONField(
        default=list,
        blank=True,
        verbose_name="附加槽位",
        help_text='JSON 数组，每项形如 {"key":"原受理法院","label":"原受理法院","hint":"","source":"slot"}；'
        "既是起草素材（喂给模型），也是律师必须补齐的事实清单",
    )
    ai_brief: Any = models.TextField(
        blank=True,
        default="",
        verbose_name="写作要点",
        help_text="交给模型的边界说明（只陈述什么、不做什么、引哪条法）；没有它模型会开始自由发挥",
    )
    is_active: Any = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    if TYPE_CHECKING:
        skeleton_template_id: int | None

    class Meta:
        app_label = "documents"
        verbose_name = "文书起草规格"
        verbose_name_plural = "文书起草规格"
        ordering: ClassVar = ["family", "doc_type"]
        indexes: ClassVar = [
            models.Index(fields=["family", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.doc_type})"
