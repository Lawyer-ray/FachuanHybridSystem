"""文档版本链：把 `[修订版]V1_日期` 的文件名约定变成真实的关系。

**为什么需要**：版本信息原先只活在文件名里。律师要看「这份合同改过几轮、
客户回稿是哪一版、AI 那版还在不在」，只能靠肉眼比文件名——改个名字就断链，
排序也只对同一天有效。

这里把每次产出一个版本节点挂钩：

- **原始来稿**（`original`）：客户送来的那份；
- **AI 审查产物**（`ai`）：流水线跑完的 `[修订版]V1_日期`；
- **律师编辑保存**（`lawyer`）：OnlyOffice 保存回写的 `-律编vN`；
- **客户回稿**（`client`）：客户改了发回来的（人工上传，可选）。

节点之间用 `parent` 串成链（不是平铺列表）：编辑器保存会产生分叉
（同一版被两个律师同时改），父子关系才是真实结构。`version_no` 是给人看的
序号（1,2,3…），`parent` 才是机器用来推「这版从哪来」的。

**为什么不复用 EditorSession**：那是**会话**（谁开着编辑器），一次会话可能
保存多次、也可能一次都没保存；版本链是**产物**（文件内容）。两者生命周期不同，
混在一张表里会让「开了编辑器但没改」凭空多出一个版本。
"""

from __future__ import annotations

import uuid

from django.db import models

from .review_task import ReviewTask


class VersionKind(models.TextChoices):
    ORIGINAL = "original", "客户来稿"
    AI = "ai", "AI 修订版"
    LAWYER = "lawyer", "律师编辑版"
    CLIENT = "client", "客户回稿"


class DocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        ReviewTask,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name="审查任务",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="上一版",
        help_text="从哪一版改出来的；空表示这是链头（通常是客户来稿）",
    )
    kind = models.CharField(
        max_length=16,
        choices=VersionKind.choices,
        default=VersionKind.AI,
        verbose_name="版本来源",
    )
    version_no = models.IntegerField(default=1, verbose_name="版本序号", help_text="给人看的 1,2,3…")
    file_path = models.CharField(
        max_length=512,
        blank=True,
        default="",
        verbose_name="文件路径",
        help_text="MEDIA_ROOT 相对路径；被清理后可能为空，但节点保留以维持链完整",
    )
    file_name = models.CharField(max_length=256, blank=True, default="", verbose_name="原始文件名")
    author = models.CharField(max_length=128, blank=True, default="", verbose_name="产生这一版的人/系统")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="说明")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "文档版本"
        verbose_name_plural = "文档版本"
        ordering = ["task", "version_no", "created_at"]
        indexes = [
            models.Index(fields=["task", "version_no"]),
            models.Index(fields=["task", "kind"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["task", "version_no"], name="uniq_version_no_per_task"),
        ]

    def __str__(self) -> str:
        return f"{self.task_id} V{self.version_no} ({self.get_kind_display()})"
