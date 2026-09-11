"""LLM 平台（供应商）配置模型。"""

from __future__ import annotations

from django.db import models


class LLMProvider(models.Model):
    """OpenAI-compatible 平台配置。

    一个平台对应一个 OpenAI-compatible API 服务（如律所自建 vLLM、小米、Moonshot 等）。
    每个平台可配置多个 API Key 以提升并发上限，并可设置每个 Key 的并发数限制。
    """

    id: int

    name = models.CharField(max_length=50, unique=True, verbose_name="平台名称")
    base_url = models.CharField(max_length=500, verbose_name="API 地址")
    api_keys = models.TextField(blank=True, default="", verbose_name="API Keys")
    default_model = models.CharField(max_length=100, verbose_name="默认模型")
    extra_models = models.TextField(blank=True, default="", verbose_name="模型列表")
    embedding_model = models.CharField(max_length=100, blank=True, default="", verbose_name="向量模型")
    timeout = models.PositiveIntegerField(default=120, verbose_name="超时（秒）")
    concurrency_per_key = models.PositiveIntegerField(default=0, verbose_name="每 Key 并发上限")
    priority = models.PositiveIntegerField(default=10, verbose_name="优先级")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["priority", "name"]
        verbose_name = "AI 平台"
        verbose_name_plural = "AI 平台"

    def __str__(self) -> str:
        return self.name

    def parsed_api_keys(self) -> list[str]:
        """按行解析 API Keys（含逗号/分号分隔兼容）。"""
        parts: list[str] = []
        for line in self.api_keys.replace(",", "\n").replace(";", "\n").splitlines():
            key = line.strip()
            if key and key.lower().startswith("bearer "):
                key = key[7:].strip()
            if key and key not in parts:
                parts.append(key)
        return parts

    def parsed_models(self) -> list[str]:
        """按逗号/换行解析模型列表。"""
        seen: list[str] = []
        for part in self.extra_models.replace("\n", ",").split(","):
            mid = part.strip()
            if mid and mid not in seen:
                seen.append(mid)
        return seen
