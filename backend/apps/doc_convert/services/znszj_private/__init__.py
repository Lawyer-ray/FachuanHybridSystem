"""znszj 私有实现包。

此目录不入库（已加入 .gitignore）。
对外暴露 get_znszj_client() 工厂函数。
"""

from __future__ import annotations

from .znszj_client import ZnszjClient


def get_znszj_client() -> ZnszjClient:
    """返回 znszj 客户端实例。"""
    return ZnszjClient()


__all__ = ["get_znszj_client"]
