"""对话附件的「页图」渲染 —— 让模型真正**看到**扫描件 / 图片。

## 为什么需要这一层

``read_agent_attachment`` 走的是文本提取链路。扫描版 PDF 没有文字层，
PyMuPDF 的 ``page.get_text()`` 返回空串而解析端点仍报 ``success=True``，
于是模型拿到 ``chars: 0`` 的正文，只能回答「我没看到内容」——用户以为
附件已发送，实际整份材料对模型不可见。

图片文件同理：``get_text()`` 对图片没有意义，必须走视觉通道。而视觉通道
要求「把页面渲染成图片交回模型」，不是文本。所以本模块只做一件事：
**把指定的页变成模型能吃的图片字节**，并把「为什么变不出来」讲清楚。

## 三层取舍

1. **页粒度决定要不要图**：PDF 的文字层判断按**页**做，不按文档做。
   一份合同常是前几页扫描件、后几页电子签，按文档判会把电子页也白渲染。
2. **体积受控**：单页长边 ≤ :data:`MAX_EDGE_PX`、单页 ≤ :data:`MAX_PAGE_BYTES`。
   超了就按 :data:`DPI_LADDER` 逐档降 dpi 重渲染；仍超限的页标
   ``too_large`` **留在结果里**，不静默丢页——丢页会让模型把缺页当「文档就这么长」。
3. **向模型隐藏失败**：渲染结果是统一的 content blocks，失败原因只进服务端日志
   与 ``RenderResult.pages``，模型看到的是「第 3 页读取失败（加密，未解密）」这类
   人话，而不是空内容。

## 缓存为什么要放独立目录

渲染一页扫描件要 100-500ms，同一份材料在一次对话里会被反复引用。缓存落在
``MEDIA_ROOT/agent_attachment_cache/``（**不**在 ``agent_attachments/`` 下）：
附件清理逻辑按 ``agent_attachments/<年>/<月>/`` 扫物理文件，缓存混在里面会被误删；
反过来缓存目录也可以整体清空而不影响任何附件记录。

缓存键 = ``(引用标识, 页码, dpi, 格式)`` 摘要。上传附件每次上传都落新 uuid
路径，attachment_id 与物理文件一一对应，天然不会脏命中；文件夹引用把源文件
``size``/``mtime`` 指纹编进引用标识（``folder_refs.render_folder_file_pages``），
源文件被替换后指纹变化、旧图自然失配。

## 子模块布局

- :mod:`.types` —— 共享类型（RenderError/RenderStrategy/RenderedPage/RenderResult）与体积常量
- :mod:`.pagespec` —— 页范围解析（parse_pages）
- :mod:`.pdf` —— PDF 逐页渲染（render_pdf_pages）
- :mod:`.image` —— 图片附件渲染（render_image）
- :mod:`.cache` —— 磁盘缓存（RenderCache/cache_root/get_cache）
- :mod:`.audit` —— 渲染审计日志（log_render）
"""

from __future__ import annotations

from .audit import log_render
from .cache import DEFAULT_CACHE_MAX_BYTES, DEFAULT_CACHE_TTL_SECONDS, RenderCache, cache_root, get_cache
from .image import render_image
from .pagespec import DEFAULT_MAX_PAGES, parse_pages
from .pdf import DPI_LADDER, MIN_TEXT_CHARS, render_pdf_pages
from .types import MAX_EDGE_PX, MAX_PAGE_BYTES, RenderedPage, RenderError, RenderResult, RenderStrategy

__all__ = [
    "MAX_EDGE_PX",
    "MAX_PAGE_BYTES",
    "DPI_LADDER",
    "MIN_TEXT_CHARS",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_CACHE_MAX_BYTES",
    "RenderError",
    "RenderStrategy",
    "RenderedPage",
    "RenderResult",
    "parse_pages",
    "render_pdf_pages",
    "render_image",
    "RenderCache",
    "cache_root",
    "get_cache",
    "log_render",
]
