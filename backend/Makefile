# 法律事务管理系统 - Backend Makefile
# ============================================================

.PHONY: help install run test migrate shell lint clean

# 默认 Python 和虚拟环境
PYTHON := venv311/bin/python
UV := uv
PYTEST := venv311/bin/pytest
MANAGE := $(PYTHON) apiSystem/manage.py

# 颜色定义
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## 显示帮助信息
	@echo "$(GREEN)法律事务管理系统 - Backend$(NC)"
	@echo ""
	@echo "可用命令:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'

# ============================================================
# 安装和配置
# ============================================================

install: ## 安装依赖 (使用 uv)
	$(UV) pip install -r requirements.txt

install-dev: ## 安装开发依赖 (使用 uv)
	$(UV) pip install -r requirements.txt
	$(UV) pip install black isort flake8 mypy

venv: ## 创建虚拟环境 (使用 uv)
	$(UV) venv venv311 --python 3.11
	@echo "$(GREEN)虚拟环境已创建，请运行: source venv311/bin/activate$(NC)"

# ============================================================
# 开发服务器
# ============================================================

run: ## 启动开发服务器 (端口 8000)
	$(MANAGE) runserver 0.0.0.0:8000

run-port: ## 启动开发服务器 (自定义端口, 使用 PORT=8001)
	$(MANAGE) runserver 0.0.0.0:$(PORT)

# ============================================================
# 数据库
# ============================================================

migrate: ## 运行数据库迁移
	$(MANAGE) migrate

makemigrations: ## 创建迁移文件
	$(MANAGE) makemigrations

migrations: makemigrations migrate ## 创建并运行迁移

showmigrations: ## 显示迁移状态
	$(MANAGE) showmigrations

resetdb: ## 重置数据库 (危险!)
	@echo "$(YELLOW)警告: 这将删除所有数据!$(NC)"
	@read -p "确认继续? [y/N] " confirm && [ "$$confirm" = "y" ]
	rm -f apiSystem/db.sqlite3
	$(MANAGE) migrate
	@echo "$(GREEN)数据库已重置$(NC)"

# ============================================================
# 用户管理
# ============================================================

superuser: ## 创建超级用户
	$(MANAGE) createsuperuser

# ============================================================
# 测试
# ============================================================

test: ## 运行测试
	PYTHONPATH=apiSystem:. $(PYTEST) tests -v --tb=short $(ARGS)

test-cov: ## 运行测试 (带覆盖率)
	PYTHONPATH=apiSystem:. $(PYTEST) tests -v --tb=short --cov=apps --cov-report=html --cov-report=term

test-fast: ## 快速测试 (不显示详情)
	PYTHONPATH=apiSystem:. $(PYTEST) tests -q

test-unit: ## 运行单元测试
	PYTHONPATH=apiSystem:. $(PYTEST) tests/unit -v --tb=short $(ARGS)

test-integration: ## 运行集成测试
	PYTHONPATH=apiSystem:. $(PYTEST) tests/integration -v --tb=short $(ARGS)

test-property: ## 运行 Property-Based Tests
	PYTHONPATH=apiSystem:. $(PYTEST) tests/property -v --tb=short $(ARGS)

test-structure: ## 运行结构验证测试
	PYTHONPATH=apiSystem:. $(PYTEST) tests/structure -v --tb=short $(ARGS)

test-admin: ## 运行 Admin 测试
	PYTHONPATH=apiSystem:. $(PYTEST) tests/admin -v --tb=short $(ARGS)

# ============================================================
# 代码质量
# ============================================================

lint: ## 代码检查
	$(PYTHON) -m flake8 apps --max-line-length=120 --ignore=E501,W503

format: ## 格式化代码
	$(PYTHON) -m black apps --line-length=120
	$(PYTHON) -m isort apps

typecheck: ## 类型检查
	$(PYTHON) -m mypy apps --ignore-missing-imports

check: lint typecheck ## 运行所有检查

# ============================================================
# Django 工具
# ============================================================

shell: ## Django Shell
	$(MANAGE) shell

dbshell: ## 数据库 Shell
	$(MANAGE) dbshell

collectstatic: ## 收集静态文件
	$(MANAGE) collectstatic --noinput

# ============================================================
# 后台任务
# ============================================================

qcluster: ## 启动 Django-Q 任务队列
	$(MANAGE) qcluster

qcluster-start: ## 启动 Django-Q 并处理待处理任务
	$(MANAGE) process_pending_tasks --reset
	$(MANAGE) qcluster

process-tasks: ## 处理待处理的爬虫任务
	$(MANAGE) process_pending_tasks

process-tasks-reset: ## 重置卡住任务并处理待处理任务
	$(MANAGE) process_pending_tasks --reset

process-tasks-dry: ## 显示待处理任务（不执行）
	$(MANAGE) process_pending_tasks --dry-run

# ============================================================
# 爬虫测试
# ============================================================

test-court-login: ## 测试法院"一张网"登录
	$(PYTHON) apps/automation/tests/test_court_zxfw_login.py

check-admin: ## 检查 Admin 配置是否正确
	$(PYTHON) scripts/check_admin_config.py

# ============================================================
# Token 管理
# ============================================================

token-example: ## 运行 Token 使用示例
	$(PYTHON) scripts/example_use_token.py

test-token: ## 测试 Token 服务
	PYTHONPATH=apiSystem:. $(PYTEST) apps/automation/tests/test_token_service.py -v

migrate-token: ## 执行 Token 相关的数据库迁移
	$(MANAGE) migrate automation
	@echo "$(GREEN)Token 数据库迁移完成$(NC)"

debug-token: ## 调试 Token 捕获问题
	$(PYTHON) scripts/debug_token_capture.py

# ============================================================
# 清理
# ============================================================

clean: ## 清理临时文件
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".DS_Store" -delete
	rm -rf htmlcov/
	rm -rf .coverage
	@echo "$(GREEN)清理完成$(NC)"

clean-logs: ## 清理日志文件
	rm -f logs/*.log
	@echo "$(GREEN)日志已清理$(NC)"

# ============================================================
# Docker (可选)
# ============================================================

docker-build: ## 构建 Docker 镜像
	docker build -t lawfirm-backend .

docker-run: ## 运行 Docker 容器
	docker run -p 8000:8000 lawfirm-backend

# ============================================================
# 健康检查
# ============================================================

health: ## 检查服务健康状态
	@curl -s http://localhost:8000/api/v1/health | python -m json.tool || echo "服务未运行"

health-detail: ## 详细健康检查
	@curl -s http://localhost:8000/api/v1/health/detail | python -m json.tool || echo "服务未运行"
