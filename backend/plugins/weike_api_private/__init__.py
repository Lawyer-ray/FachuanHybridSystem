"""
WK信息 (WKInfo) 私有 API 适配器插件

提供基于 HTTP API 的WK案例检索功能，替代默认的 Playwright 浏览器自动化方式。

安装方式：
    git clone git@<host>:<org>/fachuan-weike-private-api-plugin.git backend/plugins/weike_api_private/

功能：
    - 通过 HTTP API 直接登录WK信息系统
    - 通过 API 进行案例检索（替代 DOM 解析）
    - 支持高级检索、案由筛选、法院筛选等

注意：
    - 此插件不在主项目 Git 仓库中，需要单独获取
    - 如果插件不存在，系统会自动回退到 Playwright 方式
"""

PLUGIN_NAME = "weike_private_api"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "WK信息私有 API 适配器 - 提供基于 HTTP API 的案例检索功能"
