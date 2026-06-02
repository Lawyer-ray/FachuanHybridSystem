# 更新指南

拉取最新代码后，按你的操作系统执行对应步骤。

---

## macOS

### 更新与启动

```bash
# 1) 拉取更新
cd FachuanHybridSystem
git pull

# 2) 更新后端依赖
cd backend
make install-dev

# 3) 数据库迁移（有新 migration 时自动执行）
make migrate

# 4) 启动服务（需要两个终端）
# 终端1：Web 服务（开发模式，含热重载）
make run-dev

# 终端2：后台任务（定时任务、异步处理等）
make qcluster
```

访问 http://127.0.0.1:8002/admin/

### 开机自启动（可选）

创建两个 LaunchAgent 文件：

```bash
# Web 服务
cat > ~/Library/LaunchAgents/com.fachuan.web.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.fachuan.web</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd /Users/你的用户名/FachuanHybridSystem/backend &amp;&amp; make run-dev</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/你的用户名/FachuanHybridSystem/backend</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/fachuan-web.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/fachuan-web.log</string>
</dict>
</plist>
EOF

# 后台任务
cat > ~/Library/LaunchAgents/com.fachuan.qcluster.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.fachuan.qcluster</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd /Users/你的用户名/FachuanHybridSystem/backend &amp;&amp; make qcluster</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/你的用户名/FachuanHybridSystem/backend</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/fachuan-qcluster.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/fachuan-qcluster.log</string>
</dict>
</plist>
EOF

# 加载服务
launchctl load ~/Library/LaunchAgents/com.fachuan.web.plist
launchctl load ~/Library/LaunchAgents/com.fachuan.qcluster.plist
```

> 记得把 `你的用户名` 替换为实际用户名。日志查看：`cat /tmp/fachuan-web.log`

---

## Linux

### 更新与启动

```bash
# 1) 拉取更新
cd FachuanHybridSystem
git pull

# 2) 激活虚拟环境并更新依赖
cd backend
source .venv/bin/activate
uv sync

# 3) 数据库迁移
cd apiSystem && uv run python manage.py migrate && cd ..

# 4) 启动服务（需要两个终端）
# 终端1：Web 服务（开发模式，含热重载）
uv run python manage.py runserver 0.0.0.0:8002

# 终端2：后台任务（定时任务、异步处理等）
uv run python manage.py qcluster
```

访问 http://127.0.0.1:8002/admin/

### 开机自启动（可选）

使用 systemd 创建两个服务：

```bash
# Web 服务
sudo tee /etc/systemd/system/fachuan-web.service << 'EOF'
[Unit]
Description=Fachuan Web Server
After=network.target postgresql.service

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/home/你的用户名/FachuanHybridSystem/backend
ExecStart=/home/你的用户名/FachuanHybridSystem/backend/.venv/bin/python apiSystem/manage.py runserver 0.0.0.0:8002
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 后台任务
sudo tee /etc/systemd/system/fachuan-qcluster.service << 'EOF'
[Unit]
Description=Fachuan Q Cluster
After=network.target postgresql.service fachuan-web.service

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/home/你的用户名/FachuanHybridSystem/backend
ExecStart=/home/你的用户名/FachuanHybridSystem/backend/.venv/bin/python apiSystem/manage.py qcluster
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable --now fachuan-web fachuan-qcluster

# 查看状态
sudo systemctl status fachuan-web fachuan-qcluster
```

> 记得把 `你的用户名` 替换为实际用户名。日志查看：`journalctl -u fachuan-web -f`

---

## Windows

### 更新与启动

```powershell
# 1) 拉取更新
cd FachuanHybridSystem
git pull

# 2) 激活虚拟环境并更新依赖
cd backend
.venv\Scripts\activate
uv sync

# 3) 数据库迁移
cd apiSystem; uv run python manage.py migrate; cd ..

# 4) 启动服务（需要两个终端）
# 终端1：Web 服务（开发模式，含热重载）
uv run python manage.py runserver 0.0.0.0:8002

# 终端2：后台任务（定时任务、异步处理等）
uv run python manage.py qcluster
```

访问 http://127.0.0.1:8002/admin/

### 开机自启动（可选）

使用任务计划程序，以管理员身份运行 PowerShell：

```powershell
# Web 服务
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoExit -Command `"cd 'C:\Users\你的用户名\FachuanHybridSystem\backend'; .venv\Scripts\activate; uv run python manage.py runserver 0.0.0.0:8002`"" -WorkingDirectory "C:\Users\你的用户名\FachuanHybridSystem\backend"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "FachuanWeb" -Action $action -Trigger $trigger -Description "法穿 Web 服务" -RunLevel Highest

# 后台任务
$action2 = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoExit -Command `"cd 'C:\Users\你的用户名\FachuanHybridSystem\backend'; .venv\Scripts\activate; uv run python manage.py qcluster`"" -WorkingDirectory "C:\Users\你的用户名\FachuanHybridSystem\backend"
$trigger2 = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "FachuanQCluster" -Action $action2 -Trigger $trigger2 -Description "法穿后台任务" -RunLevel Highest
```

> 记得把 `你的用户名` 替换为实际用户名。在「任务计划程序」中可管理启停。

---

## Docker

### 更新与启动

```bash
# 1) 拉取更新
cd FachuanHybridSystem
git pull

# 2) 进入后端目录
cd backend

# 3) 重建并启动（Web + qcluster + PostgreSQL + Redis 全部自动启动）
docker compose up -d --build

# 4) 数据库迁移
docker compose exec web sh -c "cd apiSystem && uv run python manage.py migrate"
```

访问 http://localhost:8002/admin/

> Docker 模式下 qcluster 已包含在 docker-compose.yml 中，且容器自动重启（`restart: unless-stopped`），无需额外配置开机自启动。
