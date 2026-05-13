# 安装与部署指南

本文档包含法穿系统的安装、初始化、启动与常见运维命令。

## 先看这里（30 秒选路径）

- 只想最快跑起来（推荐）：直接看 **Docker 部署（推荐）**。
- 需要本地开发：先看 **本地 PostgreSQL 安装与初始化**，再看对应系统的 **本地开发** 章节。

## 目录

- Docker 部署（推荐）
- 本地 PostgreSQL 安装与初始化
- 本地开发（macOS）
- 本地开发（Linux / Windows）
- 环境变量

## Docker 部署（推荐）

适合快速体验与服务器部署。只需安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。

```bash
# 1) 克隆项目
git clone --depth 1 https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2) 配置环境变量
cp .env.example .env
# 必须修改 DJANGO_SECRET_KEY，生成命令：
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

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
git clone --depth 1 https://github.com/Lawyer-ray/FachuanHybridSystem.git
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
git clone --depth 1 https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2) 安装 uv（若未安装）
# Linux: 可直接执行下行；Windows: 请参考 https://docs.astral.sh/uv/getting-started/installation/
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3) 安装系统依赖（ddddocr / OpenCV 需要，Docker 部署已内置）
# Ubuntu / Debian（Ubuntu 22.04 用 libglib2.0-0，24.04+ 用 libglib2.0-0t64）:
sudo apt-get install -y libgl1 libglib2.0-0t64 || sudo apt-get install -y libgl1 libglib2.0-0
# CentOS / RHEL:
# sudo yum install -y mesa-libGL glib2

# 4) 创建虚拟环境并安装依赖
uv sync

# 5) 激活虚拟环境
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate

# 6) 配置环境变量
cp .env.example .env

# 7) 确保 PostgreSQL 已启动并可连接（默认读取 .env 中 DB_* 配置）
# 例如：systemctl start postgresql / brew services start postgresql / Docker 启动 postgres

# 8) 数据库迁移
cd apiSystem
uv run python manage.py migrate

# 9) 创建管理员
uv run python manage.py createsuperuser

# 10) 收集静态文件
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

