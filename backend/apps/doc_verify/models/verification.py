"""入站件核对运行与律师裁决。

## 六个状态不是六种颜色，是六份不同的法律事实

| 状态 | 事实 |
|:--|:--|
| identical | 字节相同（数字件原样回传），可硬通过 |
| verified_clean | 跑过文本层，断言全成立（附覆盖率） |
| no_difference_detected | 只跑了免费层，**未发现**差异——不等于「没改」 |
| not_requested | 策略未要求，也没人手动点 |
| changed | 红线命中或实质差异，需律师裁决 |
| unverifiable | 有页无文本可比，不给绿灯 |

把 no_difference_detected 与 verified_clean 显示成同一种绿色，等于对律师
说了一句系统并没有证据支持的话。
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class VerifyState(models.TextChoices):
    IDENTICAL = "identical", "字节相同"
    VERIFIED_CLEAN = "verified_clean", "核对通过"
    NO_DIFFERENCE_DETECTED = "no_difference_detected", "未发现差异（未做文本核对）"
    CHANGED = "changed", "疑似改动"
    UNVERIFIABLE = "unverifiable", "无法核对"
    NOT_REQUESTED = "not_requested", "未要求核对"


class VerificationRun(models.Model):
    """一次入站核对。run_key 是幂等键：同一入站字节 + 同一基线只跑一次。"""

    id: int
    artifact = models.ForeignKey(
        "doc_verify.OutboundArtifact",
        on_delete=models.CASCADE,
        related_name="verifications",
        verbose_name="出站基线",
    )
    run_key = models.CharField(max_length=80, unique=True, verbose_name="幂等键")
    state = models.CharField(max_length=24, choices=VerifyState.choices, default=VerifyState.NOT_REQUESTED)
    tier = models.PositiveSmallIntegerField(default=0, verbose_name="核对层级（0 免费层 / 1 OCR / 2 重核）")
    inbound_file_name = models.CharField(max_length=255, blank=True, default="", verbose_name="回传文件名")
    inbound_sha256 = models.CharField(max_length=64, db_index=True, verbose_name="回传字节 SHA-256")
    page_count = models.PositiveIntegerField(default=0, verbose_name="回传页数")
    #: list[dict]，形状见 domain/contracts.Finding（red / yellow / gray 三档）
    findings = models.JSONField(default=list, blank=True, verbose_name="发现项")
    #: 覆盖度：可比页 / 图片页 / 无法核对字段——不写这个数，报告就是在撒谎
    coverage = models.JSONField(default=dict, blank=True, verbose_name="覆盖度")
    source_message_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="来源材料包消息ID")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="核对时间")

    class Meta:
        verbose_name = "回传件核对"
        verbose_name_plural = "回传件核对"
        ordering: ClassVar[list[str]] = ["-created_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["artifact", "-created_at"]),
            models.Index(fields=["state", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.artifact_id}:{self.state}"


class VerificationDecision(models.Model):
    """律师裁决：**append-only**，写错就再记一条，不能改历史。

    不留痕的「放行」在出事时无法证明律师看过什么；这张表就是那份证明。
    """

    id: int
    verification = models.ForeignKey(
        "doc_verify.VerificationRun",
        on_delete=models.CASCADE,
        related_name="decisions",
        verbose_name="核对运行",
    )
    action = models.CharField(max_length=16, verbose_name="处置（accept/reject/reissue）")
    reason = models.TextField(blank=True, default="", verbose_name="理由")
    decided_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="裁决人",
    )
    decided_at = models.DateTimeField(auto_now_add=True, verbose_name="裁决时间")

    class Meta:
        verbose_name = "核对裁决"
        verbose_name_plural = "核对裁决"
        ordering: ClassVar[list[str]] = ["-decided_at", "-id"]

    def __str__(self) -> str:
        return f"{self.verification_id}:{self.action}"
