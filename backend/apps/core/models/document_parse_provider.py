"""文档解析平台（供应商）配置模型。

与 LLMProvider 同模式：一个平台对应一个解析服务商（TextinParse / MinerU），
每个平台可配置多行凭证以提升并发上限，并可设置每凭证并发数限制。
"""

from __future__ import annotations

from django.db import models


class DocumentParseProvider(models.Model):
    """文档解析平台配置。

    凭证格式按 provider_type 由对应后端定义：
    - textin: 每行一个凭证对，格式 ``app_id|secret_code``（管道符分隔，避免错位）
    - mineru: 每行一个 API Key（Bearer Token）
    未来新增解析服务时，在 provider_type choices 与 ParserFactory 注册表各加一行即可。
    """

    class ProviderType(models.TextChoices):
        TEXTIN = "textin", "TextinParse"
        MINERU = "mineru", "MinerU"

    id: int

    name = models.CharField(max_length=50, unique=True, verbose_name="平台名称")
    provider_type = models.CharField(
        max_length=20,
        choices=ProviderType.choices,
        verbose_name="解析服务",
    )
    credentials = models.TextField(blank=True, default="", verbose_name="凭证")
    concurrency_per_key = models.PositiveIntegerField(default=3, verbose_name="每凭证并发上限")
    priority = models.PositiveIntegerField(default=10, verbose_name="优先级")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["priority", "name"]
        verbose_name = "文档解析平台"
        verbose_name_plural = "文档解析平台"

    def __str__(self) -> str:
        return self.name

    def parsed_credentials(self) -> list[str]:
        """按行解析凭证（每行一个，去重保留顺序）。"""
        parts: list[str] = []
        for line in self.credentials.splitlines():
            cred = line.strip()
            if cred and cred not in parts:
                parts.append(cred)
        return parts

    @staticmethod
    def split_textin_credential(credential: str) -> tuple[str, str] | None:
        """解析 TextinParse 凭证行 ``app_id|secret_code`` 为 (app_id, secret_code)。

        Args:
            credential: 单行凭证，格式 ``app_id|secret_code``。

        Returns:
            配对元组；格式不合法时返回 None。
        """
        if "|" not in credential:
            return None
        app_id, _, secret_code = credential.partition("|")
        app_id = app_id.strip()
        secret_code = secret_code.strip()
        if not app_id or not secret_code:
            return None
        return app_id, secret_code
