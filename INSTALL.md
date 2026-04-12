# 安装与部署指南

本文档包含法穿系统的安装、初始化、启动与常见运维命令。

## 目录

- Docker 部署（推荐）
- 本地开发（macOS）
- 本地开发（Linux / Windows）
- 环境变量
- 启动顺序与运行检查

## Docker 部署（推荐）

适合快速体验与服务器部署。只需安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。

```bash
# 1) 克隆项目
git clone --depth 1 git@github.com:Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2) 配置环境变量
cp .env.example .env
# 必须修改 DJANGO_SECRET_KEY，生成命令：
#   python3 -c "import secrets; print(secrets.token_urlsafe(50))"

# 3) 构建并启动（首次会下载 Playwright 浏览器）
docker compose up -d

# 4) 等待服务就绪（migrate 完成后自动通过健康检查）
docker compose exec web sh -c "until curl -sf http://localhost:8002/admin/login/; do sleep 2; done"

# 5) 初始化管理员
docker compose exec web sh -c "cd apiSystem && uv run python manage.py createsuperuser"

# 6) 访问后台
# http://localhost:8002/admin/
```

常用命令：

```bash
docker compose logs -f          # 查看日志
docker compose down             # 停止服务
docker compose up -d --build    # 更新后重建
```

数据持久化说明：

- 数据库与上传文件已通过 Docker volume 持久化
- `docker compose down` 不会删除数据
- 如需清空：`docker compose down -v`

## 本地开发（macOS）

推荐使用 Make 命令管理流程。

```bash
# 1) 克隆项目
git clone --depth 1 git@github.com:Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2) 安装 uv（若未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或：brew install uv

# 3) 查看可用命令（可选）
make help

# 4) 创建虚拟环境（自动下载 Python 3.12）
make venv
source .venv/bin/activate

# 5) 安装依赖
make install

# 6) 配置环境变量
cp .env.example .env

# 7) 数据库迁移
make migrations

# 8) 收集静态文件
make collectstatic

# 9) 创建管理员
make superuser
```

启动服务（必须先队列后 Django）：

```bash
# 终端1
make qcluster

# 终端2
make run
# 或自定义端口
make run-port PORT=8080
```

## 本地开发（Linux / Windows）

```bash
# 1) 克隆项目
git clone --depth 1 git@github.com:Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2) 安装 uv（若未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3) 创建虚拟环境并安装依赖
uv sync

# 4) 激活虚拟环境
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate

# 5) 配置环境变量
cp .env.example .env

# 6) 数据库迁移
cd apiSystem
uv run python manage.py migrate

# 7) 创建管理员
uv run python manage.py createsuperuser

# 8) 收集静态文件
uv run python manage.py collectstatic --noinput
```

启动服务（必须先队列后 Django）：

```bash
# 终端1
uv run python manage.py qcluster

# 终端2
uv run python manage.py runserver 0.0.0.0:8002
```

## 环境变量

最小配置：

```bash
DJANGO_SECRET_KEY=请替换为强随机密钥
```

如果使用 MCP Server，还需在 `backend/.env` 配置：

```bash
FACHUAN_BASE_URL=http://127.0.0.1:8002/api/v1
FACHUAN_USERNAME=你的账号
FACHUAN_PASSWORD=你的密码
```

## 启动顺序与运行检查

启动顺序（强制建议）：

1. 先启动 `qcluster`
2. 再启动 Django Web 服务

检查点：

- 后台可访问：`http://127.0.0.1:8002/admin/`
- 任务可执行：提交一个依赖队列的任务（例如案例检索任务）后状态可从 `queued/running` 正常变化

## MCP Server（AI Agent 集成）

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

```text
tools/
├── cases/          案件（案件、当事人、日志、案号、律师指派）
├── clients/        客户（客户、财产线索）
├── contracts/      合同（合同、财务、催收提醒）
└── organization/   组织（律师、团队、OA立案）
```

新增 tool：在对应域的文件中添加函数 -> 在该域的 `__init__.py` 导出 -> 在 `server.py` 注册。

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
