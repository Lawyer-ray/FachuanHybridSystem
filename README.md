# 法穿AI案件管理系统V26.14.0

全自动处理/生成法院文书，Less is more

[English Version](README_EN.md)

## ✨ 主要功能

- **案件管理** - 案件创建、分配、进度跟踪、案号管理
- **客户管理** - 客户信息、身份证件、财产线索管理
- **合同管理** - 合同创建、补充协议、付款跟踪、律师分配
- **组织管理** - 团队、律师、账号凭证管理
- **自动化功能**
  - 法院短信解析与文书下载
  - 法院文书自动抓取
  - 财产保全保险询价
  - 飞书群消息通知
- **MCP Server** - 支持 OpenClaw 等 AI Agent 通过自然语言操作系统

## 🛠 技术栈

- **后端**: Django 6.0 + Django Ninja (API)
- **数据库**: SQLite
- **缓存**: Django 内置缓存
- **任务队列**: Django-Q2
- **浏览器自动化**: Playwright
- **包管理**: uv
- **MCP Server**: 基于 [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)，支持 AI Agent 集成

## 🚀 快速开始

### 🐳 Docker 启动（最简单，推荐）

只需要安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，无需配置 Python 环境：

```bash
# 1. 克隆项目
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，至少修改 DJANGO_SECRET_KEY

# 3. 构建并启动（首次构建约 5~10 分钟，会下载 Playwright 浏览器）
docker compose up -d

# 4. 创建管理员账号
docker compose exec web uv run python manage.py createsuperuser

# 5. 访问后台
# http://localhost:8002/admin
```

常用命令：

```bash
docker compose logs -f          # 查看日志
docker compose down             # 停止
docker compose up -d --build    # 代码更新后重新构建
```

> 数据库和上传文件通过 Docker volume 持久化，`docker compose down` 不会丢数据。
> 如需清空数据：`docker compose down -v`

---

### 🍎 macOS 用户 (本地开发，推荐使用 Make 命令)

macOS 默认支持 Make 命令，使用更简单高效：

```bash
# 1. 克隆项目
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2. 安装 uv (如果还没装)
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或: brew install uv

# 3. 查看所有可用命令（可跳过）
make help

# 4. 创建虚拟环境 (自动下载 Python 3.12，无需手动安装)
make venv
source .venv/bin/activate

# 5. 安装依赖
make install

# 5. 配置环境变量
cp .env.example .env

# 6. 数据库设置
make migrations        # 创建并运行迁移

# 7. 收集静态文件 (重要!)
make collectstatic    # 收集静态文件到正确位置

# 8. 启动服务（⚠️ 必须先启动任务队列，再启动 Django）
make qcluster       # 终端1：先启动任务队列
make run            # 终端2：再启动开发服务器 (8002端口)
# 或者
make run-port PORT=8080  # 自定义端口

# 9. 启动任务队列 (要在新终端运行)
```

### 🐧 Linux/Windows 用户

```bash
# 1. 克隆项目
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2. 安装 uv (如果还没装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 创建虚拟环境并安装依赖
uv sync

# 4. 激活虚拟环境
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 5. 配置环境变量
cp .env.example .env

# 6. 数据库迁移
cd apiSystem
python manage.py migrate

# 7. 创建管理员
python manage.py createsuperuser

# 8. 收集静态文件 (重要!)
python manage.py collectstatic --noinput

# 9. 启动开发服务器
python manage.py runserver 0.0.0.0:8002

# 10. 启动任务队列 (新终端)
python manage.py qcluster
```

## 🔧 开发环境要求

### 必需
- **包管理器**: [uv](https://docs.astral.sh/uv/)（会自动下载管理 Python 3.12，无需手动安装）
- **操作系统**: macOS (推荐) / Linux / Windows

### 推荐 (macOS)
- **Make**: 默认已安装，用于项目管理

### 安装 uv
```bash
# macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 Homebrew
brew install uv

# 验证安装
uv --version
```

## 🤖 遇到问题？让 AI 帮你

本项目所有代码完全开源。遇到任何部署、配置、使用问题，最高效的方式是**直接把项目地址丢给 AI**：

```
https://github.com/Lawyer-ray/FachuanHybridSystem
```

把这个地址和你的问题一起发给 ChatGPT、Claude、Kiro 等任何 AI，它们可以读取完整代码后给出针对性的解答，效果远比搜索引擎好。

> 代码开源意味着你可以自己动手改、自己动手查。遇到问题先读代码、问 AI，培养独立解决问题的能力。

## 🤖 MCP Server（AI Agent 集成）

通过 MCP Server，OpenClaw、Claude Desktop 等 AI Agent 工具可以用自然语言直接操作法穿系统。

### 支持的操作

| 分类 | Tool | 说明 |
|------|------|------|
| 案件 | `list_cases` | 查询案件列表 |
| 案件 | `search_cases` | 关键词搜索案件 |
| 案件 | `get_case` | 获取案件详情 |
| 案件 | `create_case` | 创建新案件 |
| 案件当事人 | `list_case_parties` | 查询案件当事人 |
| 案件当事人 | `add_case_party` | 添加案件当事人 |
| 案件日志 | `list_case_logs` | 查询案件进展日志 |
| 案件日志 | `create_case_log` | 添加案件进展日志 |
| 案号 | `list_case_numbers` | 查询案件案号 |
| 案号 | `create_case_number` | 添加案号 |
| 律师指派 | `list_case_assignments` | 查询案件律师指派 |
| 律师指派 | `assign_lawyer` | 为案件指派律师 |
| 客户 | `list_clients` | 查询客户列表 |
| 客户 | `get_client` | 获取客户详情 |
| 客户 | `create_client` | 创建新客户 |
| 客户 | `parse_client_text` | 从文本解析客户信息 |
| 客户财产 | `list_property_clues` | 查询客户财产线索 |
| 客户财产 | `create_property_clue` | 添加财产线索 |
| 合同 | `list_contracts` | 查询合同列表 |
| 合同 | `get_contract` | 获取合同详情 |
| 合同 | `create_contract` | 创建新合同 |
| 财务 | `list_payments` | 查询付款记录 |
| 财务 | `get_finance_stats` | 获取财务统计概览 |
| 催收提醒 | `list_reminders` | 查询催收提醒待办 |
| 催收提醒 | `create_reminder` | 创建催收提醒 |
| 组织架构 | `list_lawyers` | 查询律师列表 |
| 组织架构 | `list_teams` | 查询团队列表 |
| OA 立案 | `list_oa_configs` | 查询可用 OA 系统 |
| OA 立案 | `trigger_oa_filing` | 发起 OA 立案 |
| OA 立案 | `get_filing_status` | 查询立案进度 |

### 配置

在 `backend/.env` 中添加：

```bash
FACHUAN_BASE_URL=http://127.0.0.1:8002/api/v1
FACHUAN_USERNAME=你的账号
FACHUAN_PASSWORD=你的密码
```

### 启动方式

```bash
cd backend

# 开发调试（MCP Inspector）
uv run mcp dev mcp_server/server.py

# 直接运行（stdio 模式）
uv run python -m mcp_server
```

### 扩展 Tools

Tools 按业务域组织在 `backend/mcp_server/tools/` 下：

```
tools/
├── cases/          案件（案件、当事人、日志、案号、律师指派）
├── clients/        客户（客户、财产线索）
├── contracts/      合同（合同、财务、催收提醒）
└── organization/   组织（律师、团队、OA立案）
```

新增 tool：在对应域的文件中添加函数 → 在该域的 `__init__.py` 导出 → 在 `server.py` 注册。

### 在 OpenClaw / Claude Desktop 中注册

在 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "fachuan": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/FachuanHybridSystem/backend", "python", "-m", "mcp_server"]
    }
  }
}
```

## 📚 相关文档

- [更新日志](CHANGELOG.md) - 版本更新记录
- [Django 官方文档](https://docs.djangoproject.com/)
- [Django Ninja API 文档](https://django-ninja.rest-framework.com/)
- [uv 包管理器文档](https://docs.astral.sh/uv/)
- [Make 命令教程](https://www.gnu.org/software/make/manual/make.html)

## 📄 许可证

本项目采用自定义商业源码许可证：

- ✅ **免费使用**：个人（单人）或 ≤10 人团队，可免费商业使用
- 💰 **付费授权**：超过 10 人使用，按 **200 元/人** 捐赠授权

**授权方式**：通过下方微信赞赏码按人数捐赠（备注"商业授权+人数"），捐赠即视为取得授权。

详见 [LICENSE](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 💡 开源理念

前人虽未照我，但本项目必定照后人。开源利己利他，愿以此推动中国法律科技行业进步。

## 💝 致谢

本项目主要通过 **[Kiro](https://kiro.dev)** 和 **[Trae](https://trae.ai)** 两款 AI IDE 完成开发，感谢它们极大地提升了开发效率。

## 💖 支持项目

如果这个项目对你有帮助，欢迎支持项目发展：

### 微信赞赏
<img src="backend/apps/core/static/core/images/赞赏码.png" width="200" alt="微信赞赏码">

### 加密货币
- **USDT (TRC20)**: `TGs89x2uz1Qf7vALBboKcSFsZiP3J5T4h2`
- **比特币**: `bc1p39an4kulcgl8ce6lc23zd6yjv3j29uctgkt7szaxlljwjlfsq6eqll7kk8`

## 📞 联系方式

<img src="backend/apps/core/static/core/images/wechat.jpg" width="200" alt="微信二维码">

扫码添加作者微信
