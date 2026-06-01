"""
法院自动化立案/担保插件

提供一张网在线立案和诉讼保全担保的 Playwright 自动化功能。
用户需要将此插件的实现文件放置在 plugins/court_automation/ 目录下才能使用。

安装方式：
    将完整插件文件复制到 backend/plugins/court_automation/

功能：
    - 一张网 Playwright 在线立案（民事/执行）
    - 一张网诉讼保全担保申请

注意：
    - 此插件的实现文件不在 Git 仓库中，需要单独获取
    - 如果插件不存在，案件详情页不会显示「一张网立案」标签
"""

# 插件元数据
PLUGIN_NAME = "court_automation"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "法院自动化立案/担保插件 - 提供一张网 Playwright 立案和担保功能"
