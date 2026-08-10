"""
案件处理工作流 - 本地配置模板

使用方法:
1. 复制本文件为 config.py,放到工作流根目录(skills/案件处理/config.py):
   cp skills/案件处理/文件识别/assets/config.example.py skills/案件处理/config.py
2. 填入你的后端账号信息
3. config.py 已在 .gitignore 中,不会被提交

配置项会被 build_api_client()(skills/案件处理/_shared/http_client.py)作为默认值使用,
优先级:CLI 参数 > 环境变量 > config.py
"""

# 后端服务地址
BASE_URL = 'http://127.0.0.1:8002'

# JWT Token(可选,优先级高于用户名密码)
# TOKEN = 'your_jwt_token'

# 登录账号(Session 登录)
USERNAME = 'your_username'
PASSWORD = 'your_password'  # pragma: allowlist secret
