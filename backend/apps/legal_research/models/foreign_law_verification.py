"""域外法引用核验的留痕台账（append-only）。

## 为什么单独一张表

域外法核验原先**完全不落库**：结论只活在 HTTP 响应里，响应一关就没了。律师问
「上个月这条引用当时判的是什么、凭什么」时无从回答；也没法回答「这份合同引用的
域外法都核过没有」。

`LegalResearchTaskEvent` 复用不了——它必须挂 `task` 外键，而域外法核验不是检索任务。

## 三条设计约束

1. **只追加、不修改**：留痕一旦写入就不再变（所以没有 `updated_at`）。重复核验写多条，
   不做唯一约束——「同一引用今天判支持、明天判矛盾」本身就是要被看见的信息。
2. **不存条文全文**：只存 `section_text_sha256` + 长度。全文是境外法典内容，体积大且
   没必要——要复现时拿指纹与条号回 BARLC 取即可。
3. **归属不靠插件**：MCP 进程拿不到律师身份（`tool_approval_gate.py` 里明写解不出
   `user_id`），所以带身份的那一列只能由 **HTTP 入口**写。pi 直连工具路径本期不落库，
   不要拿这张表当「全量核验台账」。

## 与 `CitationCheck` 的对应关系

字段名与插件返回大体一对一，便于对照阅读；`failure_code` 是 `ok=False` 时的枚举
（`credential_missing` / `login_failed` / `verify_failed` / `timeout` …），用于把
「没配账号」和「引用不存在」分开——这两件事在审计上的含义完全相反。
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class ForeignLawVerification(models.Model):
    """一次域外法引用核验的留痕。"""

    class Verdict(models.TextChoices):
        """四档判定 + 常见失败态（与 `CitationCheck.result` 对齐）。"""

        SUPPORTED = "支持", "支持"
        CONTRADICTED = "矛盾", "矛盾"
        NOT_MENTIONED = "原文未提及", "原文未提及"
        NOT_FOUND = "不存在该引用", "不存在该引用"
        PENDING = "待判定", "待判定"

    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="foreign_law_verifications",
        verbose_name="核验人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="核验时间")

    # ---- 请求侧（当时律师/模型写下的是什么）--------------------------------
    law_name = models.CharField(max_length=255, verbose_name="引用中的法名")
    section_number = models.CharField(max_length=32, blank=True, verbose_name="条款号")
    claim = models.TextField(blank=True, verbose_name="待核验主张")
    country_code = models.CharField(max_length=32, blank=True, verbose_name="国别码")
    as_of_date = models.CharField(max_length=10, blank=True, verbose_name="引用时点")

    # ---- 结论侧 ------------------------------------------------------------
    ok = models.BooleanField(default=False, verbose_name="调用是否成功")
    failure_code = models.CharField(max_length=32, blank=True, verbose_name="失败原因枚举")
    verdict = models.CharField(
        max_length=16,
        blank=True,
        choices=Verdict.choices,
        verbose_name="判定结论",
    )
    law_title = models.CharField(max_length=512, blank=True, verbose_name="命中的法律名称")
    matched_by = models.CharField(max_length=16, blank=True, verbose_name="名称匹配方式")
    reason = models.TextField(blank=True, verbose_name="说明（原样）")
    adjudicated = models.BooleanField(default=False, verbose_name="合议是否跑过")
    unconfirmed = models.BooleanField(default=False, verbose_name="是否无结论")
    needs_human = models.BooleanField(default=False, verbose_name="是否需人工复核")
    review_reasons = models.JSONField(default=list, verbose_name="复核理由")
    agreement = models.FloatField(null=True, blank=True, verbose_name="一致度")
    elements = models.JSONField(default=list, verbose_name="逐要件判定")
    votes = models.JSONField(default=list, verbose_name="判定器摘要")
    cached = models.BooleanField(default=False, verbose_name="是否命中合议缓存")
    jury_tokens = models.IntegerField(default=0, verbose_name="合议 token（缓存命中勿重复求和）")
    judge_config = models.JSONField(default=dict, verbose_name="判定开关与模型清单")

    # ---- 溯源与版本 --------------------------------------------------------
    source_url = models.CharField(max_length=512, blank=True, verbose_name="原页地址")
    effective_date = models.CharField(max_length=32, blank=True, verbose_name="生效日")
    revise_date = models.CharField(max_length=32, blank=True, verbose_name="修订日")
    version_warnings = models.JSONField(default=list, verbose_name="时效告警")
    section_text_sha256 = models.CharField(max_length=64, blank=True, verbose_name="条文指纹")
    section_text_length = models.PositiveIntegerField(default=0, verbose_name="条文长度")
    total_ms = models.PositiveIntegerField(default=0, verbose_name="耗时（毫秒）")

    # ---- 归类（可空：只有前端知道合同上下文时才填）-------------------------
    contract_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="合同 id")
    citation_anchor = models.CharField(max_length=128, blank=True, verbose_name="合同内锚点")

    class Meta:
        verbose_name = "域外法核验留痕"
        verbose_name_plural = "域外法核验留痕"
        ordering = ["-created_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["created_by", "-created_at"], name="lr_flv_user_time_idx"),
            models.Index(fields=["contract_id", "-created_at"], name="lr_flv_contract_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.law_name}#{self.section_number} → {self.verdict or self.failure_code or '-'}"


__all__ = ["ForeignLawVerification"]
