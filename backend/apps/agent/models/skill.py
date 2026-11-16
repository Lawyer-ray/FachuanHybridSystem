"""Agent 技能偏好模型 —— 用户 × 技能 → 是否启用。

## 设计要点

- **技能库随代码发布**（``pi/skills/<name>/SKILL.md``），所有用户看到
  同一份目录；本表只记**差异**（``enabled=False`` 的行），没行的用户
  默认全启用——新增技能不需要给每个用户补一行数据。
- 与 ``AgentApprovalPolicy`` 同构：策略是用户对**工具面**的偏好层，
  这里是用户对**技能注入面**的偏好层。
- 偏好只影响「注入哪些技能目录给 pi」（见 services/skill_service），
  不影响 mcp_server 侧按名读取技能内容的工具——那个是模型主动查阅，
  与注入无关。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AgentSkillPreference(models.Model):
    """用户技能启停偏好（只记差异行）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_skill_preferences",
        verbose_name="所属用户",
    )
    #: 技能名 = 技能库目录名（Agent Skills 规范：小写字母/数字/连字符）
    skill_name = models.CharField(max_length=64, verbose_name="技能名")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "技能偏好"
        verbose_name_plural = "技能偏好"
        ordering = ["-updated_at"]
        unique_together = (("user", "skill_name"),)

    def __str__(self) -> str:
        return f"{self.user}:{self.skill_name} → {'on' if self.enabled else 'off'}"
