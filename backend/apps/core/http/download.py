"""下载响应统一构造。

解耦（2026-10-19）：Content-Disposition 的 RFC 5987 编码此前散落在
``documents/api/download_response_factory.py``、``core/api/media_protected.py``、
``message_hub/api/inbox_api.py`` 三份同体实现，另有若干处裸拼
``filename="{name}"``（中文文件名乱码、文件名内含引号/换行会破坏响应头）。
本模块收敛为唯一实现：

- ``filename="..."``：百分号编码后的 ASCII 回退（老浏览器 / 爬虫可读）；
- ``filename*=UTF-8''...``：RFC 5987 形态，现代浏览器优先解码。

两侧使用同一份编码值，文件名中的引号被编码为 ``%22``、CRLF 被编码为
``%0D%0A``，不会截断 quoted-string，也不存在响应头注入。
"""

from __future__ import annotations

from urllib.parse import quote

from django.http import HttpResponse

__all__ = ["build_download_response", "content_disposition"]


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """构造 RFC 5987 转义后的 Content-Disposition 头值。

    Args:
        filename: 原始文件名（可含中文 / 引号 / 空格 / 换行等，会被整体百分号编码）。
        inline: True 为 ``inline``（浏览器内预览），False 为 ``attachment``（下载）。
    """
    quoted = quote(filename)
    disposition = "inline" if inline else "attachment"
    return f"{disposition}; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"


def build_download_response(
    content: bytes,
    filename: str,
    content_type: str,
    *,
    inline: bool = False,
) -> HttpResponse:
    """构造带 RFC 5987 Content-Disposition 的文件下载响应。"""
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = content_disposition(filename, inline=inline)
    return response
