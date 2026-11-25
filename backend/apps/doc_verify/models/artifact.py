"""出站件基线：我们**实际发出去的那一份**长什么样。

## 为什么锚在「出站」而不是「最新定稿」

客户只会按收到的纸改。律师后来出了 V4，而客户回传的是按 V3 改的件，
拿 V4 当基线去比会全盘误报。所以基线必须在**离开我们这里的那一刻**冻结：
发邮件给客户、创建回传链接、批量打印寄送、用印 OA——四个出站事件都算。

## 为什么要存页指纹与正文两套

- 页指纹（100dpi 二值化 8px 块墨占比）：**定位**哪几页变了，不需要 OCR；
- 正文（数字 PDF / docx 的文本层）：**判定**改了什么，基线侧永远不 OCR。

只存其一都不成立：只有指纹会漏单字改动（容差 0.03 天生对单字不敏感），
只有正文则无法回答「是第几页、页序有没有动」。
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class CaptureSource(models.TextChoices):
    """基线从哪个出站动作捕获。四个动作都在仓库里真实存在。"""

    EXPORT = "export", "导出定稿"
    SEND_TO_CLIENT = "send_to_client", "发给客户"
    UPLOAD_LINK = "upload_link", "回传链接"
    PRINT = "print", "打印寄送"
    SEAL = "seal", "用印"
    MANUAL = "manual", "人工补锚"


class OutboundArtifact(models.Model):
    """一份出站文书的基线快照。**只增不改**：基线被改写等于销毁证据。"""

    id: int
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="outbound_artifacts",
        null=True,
        blank=True,
        verbose_name="案件",
    )
    doc_type = models.CharField(max_length=64, verbose_name="文书名（卷宗写法）")
    version = models.CharField(max_length=32, blank=True, default="", verbose_name="版本标签，如 V4_20261106")
    file_name = models.CharField(max_length=255, blank=True, default="", verbose_name="出站文件名")
    file_sha256 = models.CharField(max_length=64, db_index=True, verbose_name="出站字节 SHA-256")
    page_count = models.PositiveIntegerField(default=0, verbose_name="页数")
    #: 逐页指纹：list[list[float]]，与 pdf_splitting.services.split.page_fingerprint 同口径
    page_signatures = models.JSONField(default=list, blank=True, verbose_name="逐页图像指纹")
    #: 数字件的文本层（逐页拼接，分页符分隔）。扫描件为空——基线不允许来自 OCR
    text_layer = models.TextField(blank=True, default="", verbose_name="文本层")
    #: 允许变化的区域（签名/日期/盖章），形状由 area-mask 服务定义
    masks = models.JSONField(default=list, blank=True, verbose_name="允许变化区域")
    capture_source = models.CharField(
        max_length=16, choices=CaptureSource.choices, default=CaptureSource.MANUAL, verbose_name="捕获来源"
    )
    verify_required = models.BooleanField(
        default=False, verbose_name="要求回传核对", help_text="出站时勾选；决定入站件是否自动跑核对"
    )
    #: 生效策略快照：策略会变，报告必须能回答「当时按什么策略核的」
    policy_snapshot = models.JSONField(default=dict, blank=True, verbose_name="策略快照")
    captured_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="捕获人",
    )
    captured_at = models.DateTimeField(auto_now_add=True, verbose_name="捕获时间")
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="备注")

    class Meta:
        verbose_name = "出站件基线"
        verbose_name_plural = "出站件基线"
        ordering: ClassVar[list[str]] = ["-captured_at", "-id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["case", "doc_type", "-captured_at"]),
            models.Index(fields=["case", "verify_required"]),
        ]

    def __str__(self) -> str:
        version = f" {self.version}" if self.version else ""
        return f"{self.doc_type}{version} · {self.file_sha256[:8]}"
