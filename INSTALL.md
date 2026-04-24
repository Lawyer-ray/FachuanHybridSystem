# 安装与部署指南

本文档包含法穿系统的安装、初始化、启动与常见运维命令。

## 先看这里（30 秒选路径）

- 只想最快跑起来（推荐）：直接看 **Docker 部署（推荐）**。
- 需要本地开发：先看 **本地 PostgreSQL 安装与初始化**，再看对应系统的 **本地开发** 章节。
- 你是从 SQLite 升级：直接跳到 **SQLite 升级到 PostgreSQL（保留原有数据）**。
- MCP 仅在你要对接 AI Agent 时需要：可最后看 **附录（可选）：MCP Server**。

## 目录

- Docker 部署（推荐）
- 本地 PostgreSQL 安装与初始化
- 本地开发（macOS）
- 本地开发（Linux / Windows）
- 环境变量
- SQLite 升级到 PostgreSQL（保留原有数据）
- 启动顺序与运行检查
- 推送前本地检查（进阶，可选）
- 附录（可选）：MCP Server（AI Agent 集成）

## Docker 部署（推荐）

适合快速体验与服务器部署。只需安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。

```bash
# 1) 克隆项目
git clone --depth 1 https://github.com/Lawyer-ray/FachuanHybridSystem.git
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

## 本地 PostgreSQL 安装与初始化

如你使用本地开发（非 Docker 全家桶），且机器上尚未安装 PostgreSQL，可按以下方式安装。

### macOS（Homebrew）

```bash
brew install postgresql@16
brew services start postgresql@16
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

### Windows

- 方案1（推荐）：从 PostgreSQL 官网下载安装器并完成初始化。
- 方案2（Chocolatey）：

```powershell
choco install postgresql --yes
```

### 初始化数据库与用户（通用）

按 `backend/.env` 里的 `DB_NAME/DB_USER/DB_PASSWORD` 保持一致（默认示例：`fachuan_dev/postgres/postgres`）：

```bash
# 先通过本地 socket（peer 认证，无需密码）设置密码
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"

# 再创建数据库
sudo -u postgres psql -c "CREATE DATABASE fachuan_dev OWNER postgres;"

# 密码设好后，后续也可通过 TCP 连接（需输入密码）
# psql -h 127.0.0.1 -U postgres -d postgres -c "..."
```

如果数据库已存在，第二条 `CREATE DATABASE` 报错可忽略。

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

# 7) 确保本地 PostgreSQL 可用（两种方式二选一）
# 方式A：已按上文安装本机 PostgreSQL，可跳过本步骤
# 方式B：用 Docker 临时起 PostgreSQL：
docker run -d --name fachuan-pg \
  -e POSTGRES_DB=fachuan_dev \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16

# 8) 应用已提交的数据库迁移
make migrate

# 9) 收集静态文件
make collectstatic

# 10) 创建管理员
make superuser
```

启动服务（Web 与 qcluster 可按任意顺序启动；涉及异步任务时需保持 qcluster 运行）：

```bash
# 终端1
make qcluster

# 终端2
make run
# 或开发热重载（已默认启用 polling 稳定模式，避免与 qcluster 并行时卡住）
make run-dev
# 或自定义端口
make run-port PORT=8080
```

## 本地开发（Linux / Windows）

```bash
# 1) 克隆项目
git clone --depth 1 git@github.com:Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2) 安装 uv（若未安装）
# Linux: 可直接执行下行；Windows: 请参考 https://docs.astral.sh/uv/getting-started/installation/
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3) 创建虚拟环境并安装依赖
uv sync

# 4) 激活虚拟环境
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate

# 5) 配置环境变量
cp .env.example .env

# 6) 确保 PostgreSQL 已启动并可连接（默认读取 .env 中 DB_* 配置）
# 例如：systemctl start postgresql / brew services start postgresql / Docker 启动 postgres

# 7) 数据库迁移
cd apiSystem
uv run python manage.py migrate

# 8) 创建管理员
uv run python manage.py createsuperuser

# 9) 收集静态文件
uv run python manage.py collectstatic --noinput
```

启动服务（Web 与 qcluster 可按任意顺序启动；涉及异步任务时需保持 qcluster 运行）：

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
DB_ENGINE=postgresql
DB_NAME=fachuan_dev
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=127.0.0.1
DB_PORT=5432
```

如果使用 MCP Server，还需在 `backend/.env` 配置：

```bash
FACHUAN_BASE_URL=http://127.0.0.1:8002/api/v1
FACHUAN_USERNAME=你的账号
FACHUAN_PASSWORD=你的密码
```

## SQLite 升级到 PostgreSQL（保留原有数据）

适用于：你之前在本机用 `SQLite` 跑过系统，现在要切到 `PostgreSQL` 并保留历史数据。

```bash
# 0) 进入项目并激活虚拟环境
cd backend
source .venv/bin/activate

# 1) 停掉本地服务（避免迁移过程中继续写入）
pkill -f qcluster || true
pkill -f uvicorn || true

# 2) 备份 SQLite 与媒体文件
TS=$(date +%Y%m%d_%H%M%S)
BK=/tmp/fachuan_backup_$TS
mkdir -p "$BK"
cp apiSystem/db.sqlite3 "$BK/db.sqlite3.bak"
cp -R apiSystem/media "$BK/media.bak" 2>/dev/null || true

# 3) 从 SQLite 导出数据（排除系统表，避免 contenttypes 外键冲突）
DB_ENGINE=sqlite DATABASE_PATH=apiSystem/db.sqlite3 \
PYTHONPATH=apiSystem:. .venv/bin/python apiSystem/manage.py dumpdata \
  --exclude contenttypes \
  --exclude auth.permission \
  --exclude admin.logentry \
  --exclude sessions.session \
  --indent 2 > "$BK/data.json"

# 4) 切到 PostgreSQL（按本机实际账号调整）
export DB_ENGINE=postgresql
export DB_NAME=fachuan_dev
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_HOST=127.0.0.1
export DB_PORT=5432

# 5) 迁移表结构
PYTHONPATH=apiSystem:. .venv/bin/python apiSystem/manage.py migrate

# 6) 导入历史数据
PYTHONPATH=apiSystem:. .venv/bin/python apiSystem/manage.py loaddata "$BK/data.json"

# 7) 重置序列（避免后续插入主键冲突）
PYTHONPATH=apiSystem:. .venv/bin/python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
django.setup()
from django.apps import apps
from django.core.management.color import no_style
from django.db import connection
models=[m for m in apps.get_models() if m._meta.managed and not m._meta.proxy and not m._meta.auto_created]
sqls=connection.ops.sequence_reset_sql(no_style(), models)
with connection.cursor() as cur:
    for s in sqls:
        cur.execute(s)
print('sequence_reset_sql_count', len(sqls))
PY
```

> 完成后建议把 `backend/.env` 的 `DB_ENGINE/DB_*` 固定到 PostgreSQL，避免回落到 SQLite。

## 启动顺序与运行检查

启动建议：

- Django Web 与 `qcluster` 启动顺序不限。
- 若需执行依赖队列的功能（如案例检索、自动化下载等），请确保 `qcluster` 正在运行。

检查点：

- 后台可访问：`http://127.0.0.1:8002/admin/`
- 任务可执行：提交一个依赖队列的任务（例如案例检索任务）后状态可从 `queued/running` 正常变化

## 推送前本地检查（进阶，可选）

```bash
cd backend
source .venv/bin/activate

# 1) Django 基础检查
PYTHONPATH=apiSystem:. .venv/bin/python apiSystem/manage.py check
PYTHONPATH=apiSystem:. .venv/bin/python apiSystem/manage.py migrate --check

# 2) 迁移后冒烟（本地链路）
PYTHONPATH=apiSystem:. .venv/bin/python apiSystem/manage.py smoke_check --skip-admin --skip-websocket --skip-q

# 3) CI 预检（与 GitHub 主流程对齐）
TEST_DB_USER=postgres TEST_DB_PASSWORD=postgres \
DB_USER=postgres DB_PASSWORD=postgres \
DB_NAME=fachuan_ci_test TEST_DB_NAME=fachuan_ci_test \
DB_HOST=127.0.0.1 TEST_DB_HOST=127.0.0.1 \
DB_PORT=5432 TEST_DB_PORT=5432 \
make ci-check-full

# 4) 防止误提交本地敏感文件
cd ..
git ls-files '*.env' '*sqlite*' '*.sqlite3-shm' '*.sqlite3-wal'
git status --short --ignored | grep -E 'backend/\.env|db\.sqlite3|sqlite3-(shm|wal)' || true
```

通过标准：

- `check` / `migrate --check` / `smoke_check` / `ci-check-full` 全部成功
- `git ls-files` 不出现本地 `.env`、`db.sqlite3`、`db.sqlite3-shm/wal` 等文件

## 附录（可选）：MCP Server（AI Agent 集成）

仅当你需要对接 AI Agent（如 OpenClaw、Claude Desktop）时再阅读本节；普通部署与本地开发可跳过。

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
