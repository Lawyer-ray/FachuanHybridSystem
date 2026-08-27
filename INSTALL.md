# 安装与部署指南

本文档包含法穿系统的安装、初始化、启动与常见运维命令。

> **最快的安装方式**：把本仓库地址和这份 INSTALL.md 丢给 AI Agent（WorkBuddy、Claude Code、Cursor 等），让它帮你执行安装。遇到报错也直接贴给它——AI Agent 处理环境问题比人快得多。
>
> 示例：帮我安装https://github.com/Lawyer-ray/FachuanHybridSystem# 并设置初始管理员的账号和密码（法穿，1234qwer）

## 1. Docker 部署（推荐）

适合快速体验与服务器部署。只需安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。

> **新手必读（平台差异）**
> - **macOS / Linux**：装好 Docker Desktop（或 Docker Engine）即可，无需额外步骤，直接从 [1.1](#11-配置镜像加速器国内用户必做) 开始。
> - **Windows**：Docker 在 Windows 上跑本项目这种 **Linux 容器**，**必须依赖 WSL2** 作为底层引擎（老一代 Hyper-V 后端已废弃，Windows 容器又跑不了 Linux 镜像）。**请先按下面 1.0 装好 WSL2，否则 `docker compose` 会直接报错。**

### 1.0 Windows 前置：安装 WSL2（仅 Windows 需要）

WSL2 只是 Docker 的「后台引擎」，**你全程还是在普通 Windows 终端里敲 Docker 命令，不需要进 Linux 环境操作**。安装只需一条命令：

1. **以管理员身份**打开 PowerShell（开始菜单搜「PowerShell」→ 右键「以管理员身份运行」）。
2. 执行（自动安装 WSL2 内核 + 默认 Ubuntu 发行版）：

   ```powershell
   wsl --install
   ```

3. **重启电脑**一次，让 WSL2 内核生效。
4. 重启后验证是否成功（能看到版本号即正常）：

   ```powershell
   wsl --version
   ```

5. 确认默认版本为 2（避免个别机器默认是 1）：

   ```powershell
   wsl --set-default-version 2
   ```

> 常见问题：
> - 若提示「无法解析服务器」，先确认已联网；公司内网可改用 `wsl --install -d Ubuntu` 指定发行版。
> - 想更新/修复 WSL2：`wsl --update`；想重装：`wsl --unregister Ubuntu` 后重跑 `wsl --install`。
> - **强烈建议把项目克隆进 WSL 的文件系统**（见 1.2 步骤 1 的「Windows 推荐做法」），可顺带规避 Windows 换行符(CRLF)把 `docker-entrypoint.sh` 脚本搞挂的经典坑。

完成 1.0 后，回到正常 Windows 终端（无需管理员）继续下面的步骤即可。

### 1.1 配置镜像加速器（国内用户必做）

国内访问 Docker Hub 经常超时（`Get "https://registry-1.docker.io/v2/": EOF`），需配置镜像源。

编辑 Docker 配置文件：
- macOS / Windows：Docker Desktop → Settings → Docker Engine
- Linux：`/etc/docker/daemon.json`

添加 `registry-mirrors`：

```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me",
    "https://docker.m.daocloud.io"
  ]
}
```

保存后重启 Docker Desktop（或 `sudo systemctl restart docker`），再执行后续步骤。

### 1.2 启动服务

> **Windows 用户：推荐在 WSL 里执行后续命令**（规避 CRLF 与磁盘性能问题）：
> 1. 打开 PowerShell，输入 `wsl` 进入 Linux 子系统；
> 2. 进入家目录并克隆（`git clone` 下来默认就是 LF 换行，不会破坏 `.sh` 脚本）：
>    ```bash
>    cd ~
>    git clone --depth 1 https://github.com/Lawyer-ray/FachuanHybridSystem.git
>    cd FachuanHybridSystem/backend
>    ```
> 3. 之后的 `docker compose` 命令仍在 WSL 终端里跑，`docker` 会自动连到 Windows 上的 Docker Desktop。
>
> 如果你坚持在 Windows 原生终端(Cmd/PowerShell)操作，请确保用 **Git Bash** 或 PowerShell 执行、且克隆前已 `git config --global core.autocrlf input`，否则 `docker-entrypoint.sh` 可能因 CRLF 换行符启动失败。
>
> 本项目不依赖 `backend/plugins` 子模块，**无需** `--recurse-submodules`，直接 `git clone` 即可（相关高级功能会静默降级，不影响主流程）。

```bash
# 1) 克隆项目（Windows 用户请在上一步的 WSL 终端里执行，不要带 --recurse-submodules）
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
- 缓存/消息队列使用 Valkey（docker-compose 内已配置），数据通过 `redis-data` 卷持久化
- `docker compose down` 不会删除数据
- 如需清空：`docker compose down -v`

## 2. 本地开发（macOS）

推荐使用 Make 命令管理流程。

### 2.1 安装 PostgreSQL

```bash
brew install postgresql@16
brew services start postgresql@16
```

### 2.2 安装 Valkey（推荐）

项目使用 Valkey（Redis 的开源替代）作为缓存/消息队列后端。本地开发可跳过（自动降级为内存缓存），但多进程协作和定时任务需要 Valkey。

```bash
brew install valkey
brew services start valkey
```

验证：

```bash
valkey-cli ping
# 返回 PONG 即成功
```

如果已有 Redis 在运行，Valkey 可直接替代，无需迁移数据。

### 2.3 初始化数据库与用户

按 `backend/.env` 里的 `DB_NAME/DB_USER/DB_PASSWORD` 保持一致（默认示例：`fachuan_dev/postgres/postgres`）：

```bash
# 先通过本地 socket（peer 认证，无需密码）设置密码
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"  # pragma: allowlist secret

# 再创建数据库
sudo -u postgres psql -c "CREATE DATABASE fachuan_dev OWNER postgres;"

# 密码设好后，后续也可通过 TCP 连接（需输入密码）
# psql -h 127.0.0.1 -U postgres -d postgres -c "..."
```

如果数据库已存在，第二条 `CREATE DATABASE` 报错可忽略。

### 2.4 安装项目依赖

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

# 7) 应用已提交的数据库迁移
make migrate

# 8) 收集静态文件
make collectstatic

# 9) 创建管理员
make superuser
```

### 2.5 启动服务

Web 与 qcluster 可按任意顺序启动；涉及异步任务时需保持 qcluster 运行。

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

## 3. 本地开发（Linux）

### 3.1 安装 PostgreSQL

#### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

#### CentOS / RHEL

```bash
sudo yum install -y postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

### 3.2 安装 Valkey（推荐）

```bash
# Ubuntu / Debian
sudo apt install -y valkey
sudo systemctl enable --now valkey

# CentOS / RHEL（通过 EPEL 或源码编译）
sudo yum install -y epel-release
sudo yum install -y valkey
sudo systemctl enable --now valkey

# 或从源码编译（获取最新版本）
git clone --depth 1 https://github.com/valkey-io/valkey.git
cd valkey && make -j$(nproc)
sudo cp src/valkey-server src/valkey-cli /usr/local/bin/
```

验证：

```bash
valkey-cli ping
# 返回 PONG 即成功
```

### 3.3 初始化数据库与用户

按 `backend/.env` 里的 `DB_NAME/DB_USER/DB_PASSWORD` 保持一致（默认示例：`fachuan_dev/postgres/postgres`）：

```bash
# 先通过本地 socket（peer 认证，无需密码）设置密码
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"  # pragma: allowlist secret

# 再创建数据库
sudo -u postgres psql -c "CREATE DATABASE fachuan_dev OWNER postgres;"

# 密码设好后，后续也可通过 TCP 连接（需输入密码）
# psql -h 127.0.0.1 -U postgres -d postgres -c "..."
```

如果数据库已存在，第二条 `CREATE DATABASE` 报错可忽略。

### 3.4 安装项目依赖

```bash
# 1) 克隆项目
git clone --depth 1 https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2) 安装 uv（若未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3) 安装系统依赖（OpenCV 需要，Docker 部署已内置）
# Ubuntu 22.04 用 libglib2.0-0，24.04+ 用 libglib2.0-0t64
sudo apt-get install -y libgl1 libglib2.0-0t64 || sudo apt-get install -y libgl1 libglib2.0-0

# 4) 创建虚拟环境并安装依赖
uv sync

# 5) 激活虚拟环境
source .venv/bin/activate

# 6) 配置环境变量
cp .env.example .env

# 7) 确保 PostgreSQL 已启动并可连接
# systemctl start postgresql

# 8) 数据库迁移
cd apiSystem
uv run python manage.py migrate

# 9) 创建管理员
uv run python manage.py createsuperuser

# 10) 收集静态文件
uv run python manage.py collectstatic --noinput
```

### 3.5 启动服务

Web 与 qcluster 可按任意顺序启动；涉及异步任务时需保持 qcluster 运行。

```bash
# 终端1
uv run python manage.py qcluster

# 终端2
uv run python manage.py runserver 0.0.0.0:8002
```

## 4. 本地开发（Windows）

### 4.1 安装 PostgreSQL

从 [PostgreSQL 官网](https://www.postgresql.org/download/windows/) 下载安装器，安装时记住设置的密码。

或使用 Chocolatey：

```powershell
choco install postgresql --yes
```

安装完成后**重启终端**，确保 `psql` 命令可用。

### 4.2 安装 Valkey（推荐）

从 [Valkey 官网](https://valkey.io/download/) 下载 Windows 版本，或使用 WSL2：

```powershell
# WSL2 方式（推荐）
wsl sudo apt install -y valkey
wsl sudo service valkey start
wsl valkey-cli ping  # 返回 PONG 即成功

# 或使用 Chocolatey（如有可用包）
# choco install valkey --yes
```

验证：

```powershell
wsl valkey-cli ping
# 返回 PONG 即成功
```

### 4.3 初始化数据库与用户

按 `backend/.env` 里的 `DB_NAME/DB_USER/DB_PASSWORD` 保持一致（默认示例：`fachuan_dev/postgres/postgres`）：

```powershell
# 通过 psql 连接（输入安装时设置的密码）
psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'postgres';"  # pragma: allowlist secret
psql -U postgres -c "CREATE DATABASE fachuan_dev OWNER postgres;"
```

如果数据库已存在，第二条 `CREATE DATABASE` 报错可忽略。

### 4.4 安装项目依赖

> 前置条件：Python 3.12+（`uv sync` 会自动下载，无需手动安装）

```powershell
# 1) 克隆项目
git clone --depth 1 https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem\backend

# 2) 安装 uv（若未安装）
# 参考 https://docs.astral.sh/uv/getting-started/installation/
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# 安装后需重启终端，确保 uv 加入 PATH

# 3) 创建虚拟环境并安装依赖
uv sync

# 4) 激活虚拟环境
.venv\Scripts\activate

# 5) 配置环境变量
copy .env.example .env

# 6) 数据库迁移
cd apiSystem
uv run python manage.py migrate

# 7) 创建管理员
uv run python manage.py createsuperuser

# 8) 收集静态文件
uv run python manage.py collectstatic --noinput
```

### 4.5 启动服务

```powershell
# 终端1
uv run python manage.py qcluster

# 终端2
uv run python manage.py runserver 0.0.0.0:8002
```
