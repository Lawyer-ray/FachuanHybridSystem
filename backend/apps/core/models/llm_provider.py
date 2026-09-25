"""LLM 平台（供应商）配置模型。"""

from __future__ import annotations

from django.db import models

_BEARER_PREFIX = "bearer "
_MODEL_SEPARATOR = ","


def _normalize_key(raw: str) -> str:
    """去掉首尾空白与可选的 ``Bearer `` 前缀。"""
    key = raw.strip()
    if key.lower().startswith(_BEARER_PREFIX):
        key = key[len(_BEARER_PREFIX) :].strip()
    return key


def _split_models(raw: str) -> list[str]:
    """按逗号/分号拆分模型白名单，去重保序。"""
    models: list[str] = []
    for part in raw.replace(";", _MODEL_SEPARATOR).split(_MODEL_SEPARATOR):
        model_id = part.strip()
        if model_id and model_id not in models:
            models.append(model_id)
    return models


def parse_key_entries(raw: str) -> list[tuple[str, list[str]]]:
    """解析 API Keys 文本为 ``(key, 模型白名单)`` 列表。

    支持两种行格式，**以行内是否含 ``|`` 区分**：

    - ``key``：该 Key 不限模型（向后兼容旧格式）
    - ``key|model1,model2``：该 Key 仅可用于列出的模型

    不含 ``|`` 的行沿用旧语义——按逗号/分号拆成多个 Key（旧配置可能把多个
    Key 写在同一行）。含 ``|`` 的行内逗号只用于分隔模型，不再拆 Key。

    Args:
        raw: ``LLMProvider.api_keys`` 的原始文本。

    Returns:
        去重后的 ``(key, models)`` 列表；``models`` 为空表示不限模型。
    """
    entries: list[tuple[str, list[str]]] = []
    seen: set[str] = set()

    def _append(key: str, models: list[str]) -> None:
        if key and key not in seen:
            seen.add(key)
            entries.append((key, models))

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "|" in stripped:
            raw_key, _, raw_models = stripped.partition("|")
            _append(_normalize_key(raw_key), _split_models(raw_models))
            continue
        for segment in stripped.replace(";", ",").split(","):
            _append(_normalize_key(segment), [])

    return entries


class LLMProvider(models.Model):
    """OpenAI-compatible 平台配置。

    一个平台对应一个 OpenAI-compatible API 服务（如律所自建 vLLM、小米、Moonshot 等）。
    每个平台可配置多个 API Key 以提升并发上限，并可设置每个 Key 的并发数限制。

    ``api_keys`` 每行支持 ``key`` 或 ``key|model1,model2`` 两种写法，后者声明该 Key
    仅可用于列出的模型（网关按 Key 授权不同模型时使用）；不含 ``|`` 表示不限模型。
    """

    id: int

    name = models.CharField(max_length=50, unique=True, verbose_name="平台名称")
    base_url = models.CharField(max_length=500, verbose_name="API 地址")
    api_keys = models.TextField(blank=True, default="", verbose_name="API Keys")
    default_model = models.CharField(max_length=100, verbose_name="默认模型")
    extra_models = models.TextField(blank=True, default="", verbose_name="模型列表")
    embedding_model = models.CharField(max_length=100, blank=True, default="", verbose_name="向量模型")
    timeout = models.PositiveIntegerField(default=120, verbose_name="超时（秒）")
    concurrency_per_key = models.PositiveIntegerField(default=3, verbose_name="每 Key 并发上限")
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
        """按行解析 API Keys（含逗号/分号分隔兼容，忽略模型白名单）。"""
        return [key for key, _ in self.parsed_key_entries()]

    def parsed_key_entries(self) -> list[tuple[str, list[str]]]:
        """解析 API Keys 及其模型白名单。

        格式见 :func:`parse_key_entries`。``models`` 为空表示该 Key 不限模型。
        """
        return parse_key_entries(self.api_keys)

    def parsed_key_model_scopes(self) -> dict[str, list[str]]:
        """返回 ``{key: 模型白名单}``；不限模型的 Key 不出现在结果中。"""
        return {key: models for key, models in self.parsed_key_entries() if models}

    def parsed_models(self) -> list[str]:
        """按逗号/换行解析模型列表。"""
        seen: list[str] = []
        for part in self.extra_models.replace("\n", ",").split(","):
            mid = part.strip()
            if mid and mid not in seen:
                seen.append(mid)
        return seen
