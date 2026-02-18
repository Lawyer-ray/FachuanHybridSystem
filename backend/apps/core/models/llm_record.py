"""
LLM 调用记录模型

记录每次 LLM API 调用的详细信息,用于监控使用量和成本分析.
"""

from typing import ClassVar

from django.db import models


class LLMCallRecord(models.Model):
    """
    LLM 调用记录(用于成本追踪)

    记录每次 LLM API 调用的详细信息,用于监控使用量和成本分析.

    Requirements: 6.1, 6.2
    """

    id: int
    model = models.CharField(max_length=100, verbose_name="模型")
    prompt_tokens = models.IntegerField(verbose_name="输入 Token")
    completion_tokens = models.IntegerField(verbose_name="输出 Token")
    total_tokens = models.IntegerField(verbose_name="总 Token")
    duration_ms = models.FloatField(verbose_name="耗时(ms)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="调用时间")

    class Meta:
        verbose_name = "LLM 调用记录"
        verbose_name_plural = "LLM 调用记录"
        indexes: ClassVar = [
            models.Index(fields=["created_at"], name="core_llmcal_created_830747_idx"),
            models.Index(fields=["model"], name="core_llmcal_model_df0279_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.model} - {self.total_tokens} tokens - {self.created_at}"
