# Backend 快速启动指南

## 🚀 启动服务器

### 方式 1: 使用虚拟环境直接运行
```bash
backend/venv311/bin/python backend/apiSystem/manage.py runserver 0.0.0.0:8000
```

### 方式 2: 使用 Makefile（推荐）
```bash
cd backend
make run          # 默认端口 8000
make run PORT=8001  # 自定义端口
```

## 📍 重要端点

- **API 健康检查**: http://localhost:8000/api/v1/health
- **Admin 后台**: http://localhost:8000/admin/
- **API 文档**: http://localhost:8000/api/docs

## 🛠️ 常用命令

### 数据库操作
```bash
cd backend
make migrate              # 运行迁移
make makemigrations       # 创建迁移
make migrations           # 创建并运行迁移
make superuser            # 创建超级用户
```

### 测试
```bash
cd backend
make test                 # 运行测试
make test-cov            # 带覆盖率的测试
make test-fast           # 快速测试
```

### 后台任务
```bash
cd backend
make qcluster            # 启动任务队列
make process-tasks       # 处理待处理任务
```

### 清理
```bash
cd backend
make clean               # 清理临时文件
make clean-logs          # 清理日志
```

### 工具脚本
```bash
cd backend
make check-admin         # 检查 Admin 配置
make test-court-login    # 测试法院登录
```

## 📦 虚拟环境

项目使用 Python 3.11 虚拟环境：
- 位置: `backend/venv311/`
- Python: 3.11.10
- Django: 5.2.8

### 激活虚拟环境（可选）
```bash
source backend/venv311/bin/activate
```

### 安装/更新依赖
```bash
cd backend
make install             # 安装依赖
make install-dev         # 安装开发依赖
```

## 🔍 健康检查

```bash
# 简单检查
curl http://localhost:8000/api/v1/health

# 详细检查
curl http://localhost:8000/api/v1/health/detail | python3 -m json.tool
```

## 📝 开发工作流

1. **启动服务器**
   ```bash
   cd backend && make run
   ```

2. **在另一个终端启动任务队列**（如需要爬虫功能）
   ```bash
   cd backend && make qcluster
   ```

3. **运行测试**
   ```bash
   cd backend && make test
   ```

## 🐛 故障排查

### 端口被占用
```bash
# 查找占用端口的进程
lsof -i :8000

# 杀死进程
kill -9 <PID>
```

### 数据库问题
```bash
cd backend
make resetdb             # 重置数据库（会删除所有数据！）
```

### 依赖问题
```bash
cd backend
backend/venv311/bin/pip install -r requirements.txt
```

## 📚 更多信息

- 查看 `Makefile` 了解所有可用命令
- 查看 `PROJECT_CLEANUP_SUMMARY.md` 了解项目结构
- 查看各应用的 README 了解具体功能
