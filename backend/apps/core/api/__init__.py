"""
Core API 模块

提供核心功能的 API 接口.
"""

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

# 创建 Core 模块的路由,支持 JWT 和 Session 认证
router = Router(tags=["系统配置"], auth=JWTOrSessionAuth())

__all__ = [
    "router",
]

# 暂时为空,后续可以添加系统配置相关的 API
