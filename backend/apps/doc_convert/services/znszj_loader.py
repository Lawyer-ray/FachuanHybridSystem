"""znszj 客户端动态加载器。

优先从 plugins.doc_convert 插件加载，开源版本不可用。
"""

from __future__ import annotations

import logging
from typing import Protocol, cast, runtime_checkable

logger = logging.getLogger(__name__)

# 缓存加载结果，避免重复导入
_cached_client: ZnszjClientProtocol | None | bool = False  # False 表示未初始化


@runtime_checkable
class ZnszjClientProtocol(Protocol):
    """znszj 客户端接口协议。"""

    def convert_document(
        self,
        *,
        file_content: bytes,
        filename: str,
        mbid: str,
    ) -> bytes:
        """
        执行完整的 znszj 转换流程。

        流程：
        1. 认证：获取 signatureCode → token/mac → sbbs
        2. 上传：uploadOriginQsz（仅需 mac）
        3. 转写：text2model（需 token + mac）
        4. 保存：saveAndGetDownloadUrl（需 token + mac）
        5. 下载：download/docx（需 token + mac）

        Returns:
            转换后的 .docx 文件字节
        """
        ...


def get_znszj_client() -> ZnszjClientProtocol | None:
    """
    动态加载 znszj 客户端。

    优先从 plugins.doc_convert 插件加载。
    首次加载后缓存结果，避免重复导入。

    Returns:
        ZnszjClientProtocol 实例（如果插件已安装），否则 None
    """
    global _cached_client

    if _cached_client is not False:
        return _cached_client  # type: ignore[return-value]

    try:
        from plugins import has_doc_convert_plugin

        if not has_doc_convert_plugin():
            logger.info("doc_convert 插件未安装，要素式转换功能不可用")
            _cached_client = None
            return None

        from plugins.doc_convert import get_znszj_client as _factory

        client = cast(ZnszjClientProtocol, _factory())
        _cached_client = client
        logger.info("doc_convert 插件加载成功")
        return client
    except ImportError:
        logger.info("plugins 模块未安装，要素式转换功能不可用")
        _cached_client = None
        return None
    except Exception:
        logger.exception("doc_convert 插件加载失败")
        _cached_client = None
        return None
