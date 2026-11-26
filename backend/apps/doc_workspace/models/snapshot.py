"""文档快照：每次覆盖之前把旧内容存一份，让「改坏」变成可回滚。

## 为什么这是整个整改的前置

在它之前，**磁盘上零版本历史**：`save_file_content` 是 `os.replace` 原地覆写，
docstring 明写「不保留备份」，并说版本追溯交给 `contract_review` 的
`DocumentVersion` —— 而那个 app 即将整体移除。移除之后，「AI 改坏一次就没救」
会成为默认状态：AI 直改、编辑器保存、另存为，三条路都能覆盖原文件。

律师敢不敢让 AI 动自己的合同，取决于这一点，而不是功能多少。

## 三个设计约束

1. **快照不进绑定文件夹**（见 `MediaEntity.DOC_SNAPSHOTS`）：绑定文件夹里出现
   `_历史/` 之类目录，会让目录树变脏，也会被「归档打包」当成正文材料抓走。
2. **内容寻址 + 同 sha 复用 blob**：同一份内容反复保存（律师存了三次但没改字）
   时只占一份空间；但**每次覆盖都有一行记录**，seq 连续——时间线不能因为去重
   而断掉。
3. **快照不可编辑、不可删改**：只允许追加与读取。要「回到某一版」走
   `restore()`，它的做法是**先把当前内容再快照一份**，所以回滚本身也可回滚。
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class SnapshotReason(models.TextChoices):
    """为什么产生了这份快照（覆盖发生的原因）。"""

    EDITOR_SAVE = "editor_save", "编辑器保存回写"
    AI_REWRITE = "ai_rewrite", "AI 直改落笔"
    AI_REVIEW_APPLY = "ai_review_apply", "AI 审查结论落笔"
    RESTORE = "restore", "回滚到历史版本"


class ActorKind(models.TextChoices):
    AI = "ai", "AI"
    HUMAN = "human", "人"
    UNKNOWN = "unknown", "未记录"


class DocSnapshot(models.Model):
    """某个文件夹文件在某一时刻的完整内容。"""

    id: int

    owner_kind: Any = models.CharField(
        "所属文件夹类型",
        max_length=16,
        # 与 ContractWritePatch / 后续 ReviewRun 同一套坐标：kind + id + subpath
        choices=[("contract", "合同"), ("case", "案件")],
        db_index=True,
    )
    owner_id: Any = models.IntegerField("所属合同/案件 ID", db_index=True)
    subpath: Any = models.CharField("文件夹内相对路径（posix）", max_length=1000)

    seq: Any = models.IntegerField(
        "该文件的第几版快照（从 1 起连续）",
        help_text="同一 (owner_kind, owner_id, subpath) 内递增；恢复历史版本也会占用一个新 seq",
    )
    sha256: Any = models.CharField("内容 sha256（内容寻址，同 sha 复用 blob）", max_length=64, db_index=True)
    size: Any = models.BigIntegerField("字节数", default=0)
    source_mtime: Any = models.FloatField(
        "覆盖前原文件的 mtime",
        null=True,
        blank=True,
        help_text="回滚时的乐观锁依据：先确认磁盘还是不是当初那份，再决定覆盖",
    )
    storage_path: Any = models.CharField("快照文件的 storage 路径（MEDIA 下，不在绑定文件夹内）", max_length=500)

    reason: Any = models.CharField("产生原因", max_length=32, choices=SnapshotReason.choices)
    actor_kind: Any = models.CharField(
        "操作者类型", max_length=16, choices=ActorKind.choices, default=ActorKind.UNKNOWN
    )
    actor_id: Any = models.IntegerField("操作者 user id（AI 触发的落笔记触发人）", null=True, blank=True)

    created_at: Any = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "文档快照"
        verbose_name_plural = "文档快照"
        ordering = ["-created_at", "-id"]
        constraints: ClassVar[list[Any]] = [
            models.UniqueConstraint(
                fields=["owner_kind", "owner_id", "subpath", "seq"],
                name="uniq_doc_snapshot_seq_per_file",
            )
        ]
        indexes: ClassVar[list[Any]] = [
            models.Index(fields=["owner_kind", "owner_id", "subpath", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.owner_kind}/{self.owner_id}/{self.subpath}@v{self.seq}"
