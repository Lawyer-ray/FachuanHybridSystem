"""Module for choices."""

from django.db import models

class DocumentType(models.TextChoices):
    COMPLAINT = "complaint", "起诉状"
    DEFENSE = "defense", "答辩状"
    COUNTERCLAIM = "counterclaim", "反诉状"
    COUNTERCLAIM_DEFENSE = "counterclaim_defense", "反诉答辩状"

class SessionStatus(models.TextChoices):
    ACTIVE = "active", "进行中"
    COMPLETED = "completed", "已完成"
    CANCELLED = "cancelled", "已取消"

class MessageRole(models.TextChoices):
    USER = "user", "用户"
    ASSISTANT = "assistant", "AI助手"
    SYSTEM = "system", "系统"

class SessionType(models.TextChoices):
    DOC_GEN = "doc_gen", "文书生成"
    MOCK_TRIAL = "mock_trial", "模拟庭审"

class MockTrialMode(models.TextChoices):
    JUDGE = "judge", "法官视角"
    CROSS_EXAM = "cross_exam", "质证模拟"
    DEBATE = "debate", "辩论模拟"
    ADVERSARIAL = "adversarial", "多Agent对抗"
