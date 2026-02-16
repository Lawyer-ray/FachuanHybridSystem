"""文档处理相关 Schemas"""

from typing import Any

from pydantic import BaseModel, Field

from apps.automation.services.ai.prompts import DEFAULT_FILENAME_PROMPT


class DocumentProcessIn(BaseModel):
    file_path: str = Field(...)
    kind: str = Field(...)
    limit: int | None = None  # 文字提取限制,None时使用默认值
    preview_page: int | None = None  # PDF预览页码(从1开始),None时使用默认值


class DocumentProcessOut(BaseModel):
    image_url: str | None = None
    text_excerpt: str | None = None


class OllamaChatIn(BaseModel):
    model: str = Field(...)
    prompt: str = Field(...)
    text: str = Field(...)


class OllamaChatOut(BaseModel):
    data: dict[str, Any]


class MoonshotChatIn(BaseModel):
    model: str = Field(...)
    prompt: str = Field(...)
    text: str = Field(...)


class MoonshotChatOut(BaseModel):
    data: dict[str, Any]


class AutoToolProcessIn(BaseModel):
    file_path: str = Field(...)
    prompt: str = Field(default=DEFAULT_FILENAME_PROMPT)
    model: str = Field(default="qwen3:0.6b")
    limit: int | None = None  # 文字提取限制,None时使用默认值
    preview_page: int | None = None  # PDF预览页码(从1开始),None时使用默认值


class AutoToolProcessOut(BaseModel):
    text: str | None = None
    ollama_response: dict[str, Any] | None = None
    error: str | None = None


class AsyncTaskSubmitOut(BaseModel):
    task_id: str = Field(...)
    status: str = Field(...)
    message: str = Field(...)


class AsyncTaskStatusOut(BaseModel):
    task_id: str = Field(...)
    status: str = Field(...)
    result: Any | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
