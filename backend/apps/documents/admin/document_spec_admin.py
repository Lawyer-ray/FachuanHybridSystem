"""
文书起草规格 Admin 配置

规格是「一句话起草」的受控入口：新增一种文书 = 插一行数据，不写代码、不加 docx。
所以这里必须能编辑全部字段，否则每加一种文书都要改一次代码，受控词表就名存实亡。
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin

from apps.documents.models import DocumentSpec


class DocumentSpecForm(forms.ModelForm[DocumentSpec]):  # pragma: no cover
    """extra_slots 用 JSON 文本域编辑。

    为什么不上自定义 inline 表单：extra_slots 只有 key/label/hint/source 四个键、
    改动频率极低，四个字段的 inline 要配一套 formset + 模板；文本域 + JSON 校验
    代码量少一半，写错括号会在保存时报错，而不是静默存成一段字符串。
    """

    extra_slots = forms.JSONField(
        required=False,
        label="附加槽位",
        widget=forms.Textarea(attrs={"rows": 8, "cols": 100, "style": "font-family:monospace;"}),
        help_text='JSON 数组，形如 [{"key": "原受理法院", "label": "原受理法院", "hint": "", "source": "slot"}]',
    )

    class Meta:  # pragma: no cover
        model = DocumentSpec
        fields: str = "__all__"

    def clean_extra_slots(self) -> list[Any]:
        value = self.cleaned_data.get("extra_slots") or []
        # 类型错在保存时就拦住：解析器按 list[dict] 遍历，字符串会让整份文书变成未决项
        if not isinstance(value, list):
            raise forms.ValidationError("附加槽位必须是 JSON 数组（[] 里每项是一个对象）")
        return value


@admin.register(DocumentSpec)
class DocumentSpecAdmin(admin.ModelAdmin):  # pragma: no cover
    """文书起草规格管理"""

    form = DocumentSpecForm
    list_display = (
        "doc_type",
        "display_name",
        "family",
        "party_label",
        "folder_slot",
        "skeleton_name",
        "is_active",
        "updated_at",
    )
    list_filter = ("family", "is_active")
    search_fields = ("doc_type", "display_name", "ai_brief")
    autocomplete_fields = ("skeleton_template",)
    list_select_related = ("skeleton_template",)
    ordering = ("family", "doc_type")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("身份", {"fields": ("doc_type", "display_name", "family", "is_active")}),
        (
            "骨架与落位",
            {
                "fields": ("skeleton_template", "title_override", "folder_slot", "party_label"),
                "description": "共用骨架的文书必须填「标题覆盖」，否则出稿标题仍是骨架自带那个",
            },
        ),
        ("请求段", {"fields": ("claim_heading", "claim_source", "claim_text", "claim_slot_key")}),
        ("事实段", {"fields": ("facts_heading", "facts_source", "facts_slot_key")}),
        (
            "附加槽位",
            {
                "fields": ("extra_slots",),
                "description": "这些既是喂给模型的素材，也是律师必须补齐的事实清单；缺了会进未决项",
            },
        ),
        ("写作要点", {"fields": ("ai_brief",)}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="骨架文件", ordering="skeleton_template__name")
    def skeleton_name(self, obj: DocumentSpec) -> str:
        return obj.skeleton_template.name if obj.skeleton_template_id else "-"
