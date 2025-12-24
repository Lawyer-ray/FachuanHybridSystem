# Docker 快速启动指南

本文档帮助你快速使用 Docker 部署法穿案件管理系统。

## 前置要求

- **Docker**: 20.10 或更高版本
- **Docker Compose**: 2.0 或更高版本（Docker Desktop 已内置）
- **系统资源**: 至少 4GB 可用内存
- **磁盘空间**: 至少 10GB 可用空间

### 检查 Docker 版本

```bash
docker --version
docker compose version
```

## 快速启动（5 分钟）

### 1. 克隆项目

```bash
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd fachuang
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp docker/.env.docker.example .env

# 编辑配置文件
# macOS/Linux
nano .env
# 或使用 vim
vim .env
# Windows
notepad .env
```

**必须修改的配置**：

```bash
# 生成安全密钥（选择以下任一方式）

# 方式1: 使用 openssl（推荐，macOS/Linux 自带）
openssl rand -base64 50

# 方式2: 使用 /dev/urandom（Linux/macOS）
head -c 50 /dev/urandom | base64

# 方式3: 在线生成
# 访问 https://djecrety.ir/ 或任意密码生成器

# 将生成的密钥填入 .env 文件的 DJANGO_SECRET_KEY
DJANGO_SECRET_KEY=你生成的密钥
```

### 3. 启动服务

```bash
# 构建并启动所有服务（后台运行）
docker compose up -d

# 查看启动日志
docker compose logs -f
```

首次启动需要几分钟，系统会自动：
- 构建 Docker 镜像
- 安装 Python 依赖
- 安装 Playwright 浏览器
- 运行数据库迁移
- 初始化系统配置

### 4. 创建管理员账号

```bash
docker compose exec backend python apiSystem/manage.py createsuperuser
```

按提示输入用户名、邮箱和密码。

### 5. 访问系统

- **Admin 后台**: http://localhost:8002/admin
- **API 文档**: http://localhost:8002/api/v1/docs
- **健康检查**: http://localhost:8002/api/v1/health

## 常用命令

### 服务管理

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 重启单个服务
docker compose restart backend

# 查看服务状态
docker compose ps

# 查看服务日志
docker compose logs -f              # 所有服务
docker compose logs -f backend      # 仅后端
docker compose logs -f qcluster     # 仅任务队列
docker compose logs --tail=100 backend  # 最近 100 行
```

### 进入容器

```bash
# 进入后端容器
docker compose exec backend bash

# 运行 Django 管理命令
docker compose exec backend python apiSystem/manage.py shell
docker compose exec backend python apiSystem/manage.py dbshell
```

### 数据库操作

```bash
# 运行迁移
docker compose exec backend python apiSystem/manage.py migrate

# 创建超级用户
docker compose exec backend python apiSystem/manage.py createsuperuser

# 导出数据
docker compose exec backend python apiSystem/manage.py dumpdata > backup.json

# 导入数据
docker compose exec backend python apiSystem/manage.py loaddata backup.json
```

## 数据备份与恢复

### 备份数据

```bash
# 创建备份目录
mkdir -p backup/$(date +%Y%m%d)

# 备份数据库
docker cp fachuang-backend:/app/data/db.sqlite3 backup/$(date +%Y%m%d)/

# 备份媒体文件
docker cp fachuang-backend:/app/media backup/$(date +%Y%m%d)/

# 备份所有数据卷（推荐）
docker run --rm -v fachuang-db:/data -v $(pwd)/backup:/backup alpine \
    tar czf /backup/db_backup_$(date +%Y%m%d).tar.gz -C /data .

docker run --rm -v fachuang-media:/data -v $(pwd)/backup:/backup alpine \
    tar czf /backup/media_backup_$(date +%Y%m%d).tar.gz -C /data .
```

### 恢复数据

```bash
# 停止服务
docker compose down

# 恢复数据库
docker run --rm -v fachuang-db:/data -v $(pwd)/backup:/backup alpine \
    sh -c "rm -rf /data/* && tar xzf /backup/db_backup_20240101.tar.gz -C /data"

# 恢复媒体文件
docker run --rm -v fachuang-media:/data -v $(pwd)/backup:/backup alpine \
    sh -c "rm -rf /data/* && tar xzf /backup/media_backup_20240101.tar.gz -C /data"

# 重新启动
docker compose up -d
```

### 自动备份脚本

创建 `backup.sh`：

```bash
#!/bin/bash
BACKUP_DIR="./backup/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "开始备份..."
docker cp fachuang-backend:/app/data/db.sqlite3 "$BACKUP_DIR/"
docker cp fachuang-backend:/app/media "$BACKUP_DIR/"
echo "备份完成: $BACKUP_DIR"

# 保留最近 7 天的备份
find ./backup -type d -mtime +7 -exec rm -rf {} \; 2>/dev/null
```

## 版本更新

### 标准更新流程

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 重新构建镜像
docker compose build

# 3. 重启服务（自动运行迁移）
docker compose up -d

# 4. 查看更新日志
docker compose logs -f backend
```

### 更新前备份（推荐）

```bash
# 备份数据库
docker cp fachuang-backend:/app/data/db.sqlite3 ./backup/db_before_update.sqlite3

# 然后执行更新
git pull origin main
docker compose build
docker compose up -d
```

### 回滚到之前版本

```bash
# 停止服务
docker compose down

# 回滚代码
git checkout <之前的版本号>

# 恢复数据库（如果需要）
docker cp ./backup/db_before_update.sqlite3 fachuang-backend:/app/data/db.sqlite3

# 重新构建并启动
docker compose build
docker compose up -d
```

## 常见问题排查

### 1. 服务无法启动

**检查日志**：
```bash
docker compose logs backend
```

**常见原因**：
- 端口被占用：修改 `.env` 中的 `BACKEND_PORT`
- 内存不足：确保至少 4GB 可用内存
- SECRET_KEY 未设置：检查 `.env` 文件

### 2. 数据库迁移失败

```bash
# 查看详细错误
docker compose logs backend | grep -i error

# 手动运行迁移
docker compose exec backend python apiSystem/manage.py migrate --verbosity=2
```

### 3. Redis 连接失败

```bash
# 检查 Redis 状态
docker compose ps redis
docker compose logs redis

# 测试 Redis 连接
docker compose exec redis redis-cli ping
```

### 4. Playwright 浏览器问题

```bash
# 检查浏览器是否安装
docker compose exec backend playwright install --dry-run

# 重新安装浏览器
docker compose exec backend playwright install chromium
```

### 5. 权限问题

```bash
# 检查数据目录权限
docker compose exec backend ls -la /app/data

# 修复权限（如果需要）
docker compose exec --user root backend chown -R appuser:appgroup /app/data
```

### 6. 磁盘空间不足

```bash
# 清理未使用的 Docker 资源
docker system prune -a

# 清理未使用的卷（注意：会删除数据！）
docker volume prune
```

### 7. 健康检查失败

```bash
# 手动测试健康检查
curl http://localhost:8000/api/v1/health

# 查看健康检查日志
docker inspect fachuang-backend | grep -A 10 Health
```

## 生产环境建议

### 1. 安全配置

```bash
# .env 文件配置
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<生成的安全密钥>
DJANGO_ALLOWED_HOSTS=your-domain.com
CORS_ALLOWED_ORIGINS=https://your-frontend.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
```

### 2. 反向代理（Nginx）

项目提供了完整的 Nginx 配置示例，位于 `docker/nginx.conf.example`。

**快速配置**：

```bash
# 复制配置文件
sudo cp docker/nginx.conf.example /etc/nginx/sites-available/fachuang

# 编辑配置，修改域名和证书路径
sudo nano /etc/nginx/sites-available/fachuang

# 创建软链接
sudo ln -s /etc/nginx/sites-available/fachuang /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo nginx -s reload
```

**获取 SSL 证书（Let's Encrypt）**：

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期测试
sudo certbot renew --dry-run
```

**简化版 Nginx 配置**：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Strict-Transport-Security "max-age=63072000" always;

    # 文件上传大小限制
    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias /path/to/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /path/to/media/;
        expires 7d;
    }
}
```

详细配置请参考 `docker/nginx.conf.example`。

### 3. 资源限制

资源限制已在 `docker-compose.yml` 中配置，可通过环境变量调整：

```bash
# .env 文件配置
# Backend 服务
BACKEND_CPU_LIMIT=2.0
BACKEND_MEMORY_LIMIT=2G

# Redis 服务
REDIS_CPU_LIMIT=0.5
REDIS_MEMORY_LIMIT=512M

# Q-Cluster 服务
QCLUSTER_CPU_LIMIT=1.0
QCLUSTER_MEMORY_LIMIT=1G
```

或直接在 `docker-compose.yml` 中修改：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 4. Gunicorn 调优

Gunicorn 配置文件位于 `docker/gunicorn.conf.py`，可通过环境变量调整：

```bash
# .env 文件配置
GUNICORN_WORKERS=4          # Worker 数量
GUNICORN_THREADS=4          # 每个 Worker 的线程数
GUNICORN_TIMEOUT=120        # 请求超时时间
GUNICORN_MAX_REQUESTS=1000  # Worker 处理请求数上限
GUNICORN_LOG_LEVEL=info     # 日志级别
```

### 5. 日志管理

```bash
# 查看日志大小
docker system df -v

# 配置日志轮转（已在 docker-compose.yml 中配置）
# max-size: 50m
# max-file: 5
```

## 开发环境

如需开发环境（支持代码热重载）：

```bash
# 使用开发配置启动
docker compose -f docker-compose.dev.yml up -d

# 查看日志
docker compose -f docker-compose.dev.yml logs -f
```

## 获取帮助

- **项目文档**: 查看 `backend/docs/` 目录
- **API 文档**: http://localhost:8002/api/v1/docs
- **问题反馈**: 在 GitHub 提交 Issue

---

**版本**: 1.0.0  
**更新日期**: 2024-12
