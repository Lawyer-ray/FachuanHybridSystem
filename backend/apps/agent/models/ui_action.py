"""Agent UI 动作审计表：``confirm`` / ``guarded`` 档动作的派发与回执留痕。

## 为什么只有 confirm / guarded 落库，safe 不落

一次对话里 ``safe`` 动作（跳页、开面板、切筛选）能连发五六条，而它们**没有任何业务
副作用**：写下来只会让表随对话线性膨胀，事后追责要查的永远是「这一次写库 / 上传是谁
点的头」。所以写入口（``services/ui_action/audit.record_dispatch``）自己按 ``risk``
挡掉 safe——调用方不可能漏判。

## 为什么 ``outcome`` 默认 ``unknown`` 而不是 ``ok``

回执可能**永远不到**（页面没打开、律师切走了、前端崩了）。这张表的读者是事后审计
（「这个动作到底成了没有」）与动作历史列表。默认值定成 ``ok`` 等于把所有「没回执」
在报表里写成「成功」——法律场景里这是最不能出的错。``unknown`` 才是唯一诚实的答案：
我们发了，但我们不知道。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .session import AgentSession


class AgentUiAction(models.Model):
    """一次 UI 动作的审计行（派发时写入，回执到达后就地更新）。

    写入方只有两处，都走 ``services/ui_action/audit.py``：下发成功时插一行
    ``outcome="unknown"``，前端回执到达时按 ``call_id`` 就地更新。**没有第三种状态**——
    行数 ≠ 执行次数，它只说明「系统发出了这个动作」，结局看 ``outcome``。
    """

    #: 派发时生成的 32 位十六进制 id（``publish_ui_action`` 的 ``call_id``）。
    #: 回执按它定位那一行，所以必须唯一；唯一约束自带索引，见 :class:`Meta`。
    call_id = models.CharField(max_length=64, unique=True, verbose_name="动作调用标识")
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="ui_actions",
        null=True,
        blank=True,
        verbose_name="所属会话",
    )
    #: 动作所属用户（由会话推得）。不与会话级联删除：会话被清掉后审计仍要能回答
    #: 「谁让 AI 干过这件事」，所以是 SET_NULL 而不是 CASCADE。
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_ui_actions",
        null=True,
        blank=True,
        verbose_name="所属用户",
    )
    action = models.CharField(max_length=64, verbose_name="动作名")
    #: 下发给页面的参数原文（审批卡上律师看到的就是它，事后追责要能还原）。
    arguments = models.JSONField(default=dict, blank=True, verbose_name="动作参数")
    #: 风险档（``confirm`` / ``guarded``；``safe`` 不入库，见模块 docstring）。
    risk = models.CharField(max_length=16, verbose_name="风险档")
    #: 放行这次动作的审批人。best-effort 关联（见 ``audit.record_dispatch``）：
    #: 找不到审批行就留空，**不要**因此拒写审计——下发已经发生，那是事实。
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_ui_actions_approved",
        null=True,
        blank=True,
        verbose_name="批准人",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="批准时间")
    #: 是否有页面在收听（``publish_ui_action`` 的 ``delivered`` 口径）。
    #: 与 ``outcome`` 分开记：没送达的动作也可能收到回执（律师刚好刷新打开了页面）。
    delivered = models.BooleanField(default=False, verbose_name="已送达")
    #: 页面回执的真实结局（``ok`` / ``error`` / ``aborted``），默认 ``unknown``。
    outcome = models.CharField(max_length=16, default="unknown", verbose_name="执行结果")
    #: 失败原因码，只在 ``outcome="error"`` 时有值（别的结局带着它会被误读成故障）。
    error_code = models.CharField(max_length=32, blank=True, default="", verbose_name="失败原因码")
    #: 执行完成后页面的真实地址（``ok`` 时最能证明「页面到底在哪」）。
    observed_location = models.CharField(max_length=300, blank=True, default="", verbose_name="执行后地址")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "Agent UI 动作审计"
        verbose_name_plural = "Agent UI 动作审计"
        ordering = ["-created_at"]
        indexes = [
            # 只加这一条：``call_id`` 的 unique 约束本身就是一棵 B-tree 索引，回执按它定位
            # 已经够快；再叠一条 ``Index(fields=["call_id"])`` 只是同一棵索引的第二份拷贝
            # （每次写入多维护一份），所以这里**故意**不再声明。
            # 会话维度的索引服务「这个会话里 AI 干过什么」——按时间倒序扫最新几条。
            models.Index(fields=["session", "-created_at"], name="agent_uiaction_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} [{self.outcome}]"
