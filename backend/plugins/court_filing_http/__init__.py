"""
HTTP 链路立案插件

这是一个可插拔的插件，提供基于 HTTP API 的法院立案功能。
用户需要将此插件文件放置在 plugins/court_filing_http/ 目录下才能使用。

安装方式：
    将此目录复制到 backend/plugins/court_filing_http/

功能：
    - 通过 HTTP API 直接与法院系统交互
    - 支持民事立案、执行立案
    - 相比 Playwright 方式更稳定、更快速

注意：
    - 此插件不在 Git 仓库中，需要单独获取
    - 如果插件不存在，系统会自动回退到 Playwright 方式
"""

# 插件元数据
PLUGIN_NAME = "court_filing_http"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "HTTP 链路立案插件 - 提供基于 HTTP API 的法院立案功能"
