"""
Automation 服务模块

各子模块按需导入，避免启动时 eager import 全部服务。

子模块：
- token/: Token 管理服务
- document_delivery/: 文书送达服务
- sms/: 短信处理服务
- document/: 文书处理服务
- ai/: AI 服务
- insurance/: 保险服务
- chat/: 聊天服务
- captcha/: 验证码服务
- scraper/: 爬虫服务
"""
