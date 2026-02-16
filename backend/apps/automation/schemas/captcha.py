"""验证码识别 Schemas"""

import base64
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator


class CaptchaRecognizeIn(BaseModel):
    """验证码识别请求"""

    image_base64: str = Field(..., description="Base64 编码的图片数据", min_length=1, json_schema_extra={})

    @field_validator("image_base64")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        """验证 Base64 格式"""
        if not v or not v.strip():
            raise ValueError("图片数据不能为空")

        # 移除可能的 data URL 前缀 (e.g., "data:image/png;base64,")
        if "," in v:
            v = v.split(",", 1)[1]

        v = v.strip()

        # 验证是否为有效的 Base64 编码
        try:
            base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("无效的 Base64 编码") from None

        return v


class CaptchaRecognizeOut(BaseModel):
    """验证码识别响应"""

    success: bool = Field(..., description="是否识别成功")
    text: str | None = Field(None, description="识别出的验证码文本")
    processing_time: float | None = Field(None, description="处理耗时(秒)")
    error: str | None = Field(None, description="错误信息")

    class Config:
        json_schema_extra: ClassVar = {
            "examples": [
                {"success": True, "text": "AB12", "processing_time": 0.234, "error": None},
                {"success": False, "text": None, "processing_time": 0.012, "error": "图片格式不支持"},
            ]
        }
