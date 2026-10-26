"""OnlyOffice 编辑器会话模型。

一张表同时服务两件事：
1. **保存回写锚点**：DS 回调（status=2/6）只带 document key，靠它反查
   业务实体（当前仅 contract_review）与用户，把编辑产物落回 ReviewTask；
2. **document key 轮换**：saved_version 在每次保存回写后 +1，下次签发
   配置时据此换 key（官方要求「保存后 key 必须重新生成」），否则 DS
   继续用缓存旧内容。

task 用 UUID 弱引用而非外键——onlyoffice 不应硬依赖 contract_review
的模型层；task_type 预留未来扩展（其它业务域的文档接入时加分支即可）。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class EditorSession(models.Model):
    """一个「用户 × 业务文档」的编辑器绑定。"""

    document_key = models.CharField(
        # 只索引不唯一：同文档同版本对所有用户算出同一 key（DS 实时协同的前提），
        # 多个用户的会话会持有相同的 key；保存回写后各自轮换
        "该用户最近签发的 DS document key",
        max_length=32,
        db_index=True,
    )
    task_type = models.CharField("业务域", max_length=32, default="contract_review", db_index=True)
    task_id = models.UUIDField("业务任务 ID")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="签发用户")
    source_path = models.CharField("原始站内路径（key 哈希原料，不含签名参数）", max_length=500)
    version = models.CharField("调用方传入的内容版本标识", max_length=200, blank=True, default="")
    saved_version = models.IntegerField("保存回写轮次", default=0)
    last_callback_status = models.IntegerField("最近一次 DS 回调状态码", default=0)
    last_saved_at = models.DateTimeField("最近一次保存回写时间", null=True, blank=True)
    prev_output_file = models.CharField(
        "保存回写前的产物路径留档（物理文件保留，可手工恢复）",
        max_length=500,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "编辑器会话"
        verbose_name_plural = "编辑器会话"
        constraints = [
            models.UniqueConstraint(
                fields=["task_type", "task_id", "user"],
                name="uniq_editor_session_per_task_user",
            )
        ]

    def __str__(self) -> str:
        return f"{self.task_type}/{self.task_id} saved_v{self.saved_version}"
