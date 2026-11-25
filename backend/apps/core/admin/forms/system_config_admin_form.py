"""SystemConfig Admin 表单。"""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec
from apps.core.security.secret_display import count_segments

#: 支持多凭证的配置项（每行一个，调用时自动轮询/切换）。
#:
#: PADDLEOCR_API_TOKEN 加入原因：单 Key 有提交排队（实测 10010 队列已满），
#: 而一份 164 页卷宗串行识别要 80 分钟。多 Key 由凭证池轮询分配才能真并行。
#: 这些 key 的 secret 属性不变，只是提示文案换掉（"每行一个"而不是"留空不改"）。
#:
#: YUANDIAN_API_KEYS 加入原因：元典按 Key 维度限流（超限回 429），单 Key 撞限流
#: 时只能干等；多 Key 由数据源层轮询换下一把才能把并发用满。与 QCC / 天眼查同口径。
_MULTI_KEY_CONFIGS = {"TIANYANCHA_MCP_API_KEY", "QCC_MCP_API_KEY", "PADDLEOCR_API_TOKEN", "YUANDIAN_API_KEYS"}

#: 枚举型配置：key → ((值, 展示文案), ...)，前台渲染成下拉框而非自由文本框。
#:
#: 为什么需要：这些键的合法取值是**封闭集合**（OCR 引擎、模型、开关），自由文本会让人
#: 手输错一个字就得到运行时 500 或 400（如把 PaddleOCR-VL-1.6 写成 paddleocr_vl16）。
#: 值一律用小写下划线键（与代码里的模型表一致），展示文案写人话。
_ENUM_CONFIGS: dict[str, tuple[tuple[str, str], ...]] = {
    "OCR_PROVIDER": (
        ("paddleocr_api", "PaddleOCR 云端 API（推荐）"),
        ("local", "本地 RapidOCR（生僻字易错，仅离线备用）"),
    ),
    "PADDLEOCR_API_MODEL": (
        ("paddleocr_vl_1_6", "PaddleOCR-VL-1.6（最新，生僻字/印章增强，推荐法律文书）"),
        ("paddleocr_vl_1_5", "PaddleOCR-VL-1.5（高精度版面分析）"),
        ("paddleocr_vl", "PaddleOCR-VL（版面分析 + OCR）"),
        ("pp_structure_v3", "PP-StructureV3（文档结构化，表格/版面）"),
        ("pp_ocrv6", "PP-OCRv6（纯文字 OCR，快但生僻字易错）"),
        ("pp_ocrv5", "PP-OCRv5（纯文字 OCR，旧版）"),
    ),
    "YUANDIAN_MCP_ENABLED": (
        ("true", "开启：AI 助手挂载元典 MCP 工具"),
        ("false", "关闭：不挂载（案情不会经 AI 助手发给元典）"),
    ),
}


class SystemConfigAdminForm(forms.ModelForm):  # pragma: no cover
    class Meta:  # pragma: no cover
        model = SystemConfig
        fields = "__all__"
        widgets = {
            "value": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        super().__init__(*args, **kwargs)
        self.fields["value"].widget.attrs.setdefault("rows", 6)

        instance = self.instance
        if not instance or not instance.pk:
            return

        # 枚举型配置换成下拉框：把自由文本 Textarea 换成 Select。
        # 必须在 instance 就绪后做——新建页（无 pk）还没有 key，无从判断类型。
        # secret 优先：敏感值必须保留「留空=不修改」的文本框语义，不能变成下拉枚举。
        choices = None if instance.is_secret else _ENUM_CONFIGS.get(str(instance.key or ""))
        if choices:
            current = str(instance.value or "")
            # 库里的值若不在此次枚举中（历史遗留值），补一条以免静默丢失。
            if current and current not in {value for value, _label in choices}:
                choices = (*choices, (current, f"{current}（当前值，非标准选项）"))
            self.fields["value"] = forms.ChoiceField(
                choices=choices,
                initial=current,
                required=False,
                label="值",
                help_text="从下拉框选择；非法值会导致运行时报错。",
            )

        if instance.is_secret and instance.value:
            # 安全审计：secret 值不再回显明文（原先 try_decrypt 后经 initial 渲染进 HTML），
            # 改为"留空=不修改"：编辑页留空，clean() 时保留库中密文原值
            self.initial["value"] = ""
            self.fields["value"].help_text = "留空表示不修改原值（不回显已保存的敏感内容）"

        if instance.key in _MULTI_KEY_CONFIGS:
            hint = "支持多个 API Key，每行一个；也兼容逗号或分号分隔，调用时会自动轮询切换可用 Key。"
            # secret 配置不回显明文，用户看不到自己到底存了几个 Key。
            # 这里只报「已有 N 个」这个计数（不泄露任何片段），
            # 让他能确认多 Key 是否真的存进去了。计数口径与「已存值」页共用同一实现，
            # 避免两处各切一次导致「保存时说 3 个、查看时说 1 个」。
            if instance.is_secret and instance.value:
                count = count_segments(str(instance.value))
                if count:
                    hint += f"（当前已保存 {count} 个 Key；留空提交则保持不变）"
            self.fields["value"].help_text = hint

    def clean(self) -> dict[str, Any]:  # pragma: no cover
        """表单级清洗：secret 值加密落库。

        注意：加密必须放在表单级 clean() 而非 clean_value()——Django 按字段声明顺序
        逐个清洗，SystemConfig.value 声明在 is_secret 之前，clean_value() 执行时
        cleaned_data 里还没有 is_secret（恒为 None），加密分支永不可达。
        """
        cleaned = super().clean()
        assert cleaned is not None  # super().clean() 返回 cleaned_data，校验阶段不会为 None
        value = str(cleaned.get("value") or "")
        if not value:
            # 安全审计：编辑既有 secret 配置时留空 → 保留库中密文原值，避免清空敏感配置
            if self.instance and self.instance.pk and self.instance.is_secret and self.instance.value:
                cleaned["value"] = self.instance.value
            return cleaned
        if not bool(cleaned.get("is_secret")):
            return cleaned
        try:
            cleaned["value"] = SecretCodec().encrypt(value)
        except RuntimeError as exc:
            raise ValidationError("缺少敏感配置加密密钥，无法保存 secret 配置。") from exc
        return cleaned
