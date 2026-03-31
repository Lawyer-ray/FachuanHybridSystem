"""Module for choices."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentType(models.TextChoices):
    COMPLAINT = "complaint", _("起诉状")
    DEFENSE = "defense", _("答辩状")
    COUNTERCLAIM = "counterclaim", _("反诉状")
    COUNTERCLAIM_DEFENSE = "counterclaim_defense", _("反诉答辩状")


class SessionStatus(models.TextChoices):
    ACTIVE = "active", _("进行中")
    COMPLETED = "completed", _("已完成")
    CANCELLED = "cancelled", _("已取消")


class MessageRole(models.TextChoices):
    USER = "user", _("用户")
    ASSISTANT = "assistant", _("AI助手")
    SYSTEM = "system", _("系统")


class SessionType(models.TextChoices):
    DOC_GEN = "doc_gen", _("文书生成")
    MOCK_TRIAL = "mock_trial", _("模拟庭审")


class MockTrialMode(models.TextChoices):
    JUDGE = "judge", _("法官视角")
    CROSS_EXAM = "cross_exam", _("质证模拟")
    DEBATE = "debate", _("辩论模拟")
    ADVERSARIAL = "adversarial", _("多Agent对抗")
