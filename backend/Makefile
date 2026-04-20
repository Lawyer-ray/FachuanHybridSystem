# 法律事务管理系统 - Backend Makefile
# ============================================================

check: lint typecheck ## 运行所有检查

# ============================================================
# GitHub CI 镜像检查（推送前必跑，避免反复修 7 轮）
# ============================================================

ci-check: ## 模拟 GitHub backend (3.12) job 的核心检查（changed-files 模式）
	@echo "$(GREEN)=== GitHub CI 预检 (changed-files 模式) ===$(NC)"
	@echo ""
	@CHANGED=$$(bash devtools/changed_files.sh); \
	if [ -z "$$CHANGED" ]; then \
		echo "✅ 无变更 Python 文件"; \
	else \
		echo "🔍 [1/3] Ruff (changed files): $$CHANGED"; \
		$(PYTHON) -m ruff check $$CHANGED --config ruff.toml; \
		echo ""; \
		echo "🔍 [2/3] Mypy (changed files, follow-imports=silent): $$CHANGED"; \
		PYTHONPATH=apiSystem:. $(PYTHON) -m mypy --config-file mypy.ini --follow-imports=silent $$CHANGED; \
		echo ""; \
	fi
	@echo "🔍 [3/3] 结构测试 (ratchet guard):"
	$(TEST_ENV) $(PYTEST) tests/ci/structure/ -q --no-header $(ARGS)
	@echo ""
	@echo "$(GREEN)✅ GitHub CI 预检通过! 可以放心推送了$(NC)"

ci-check-full: ## 完整 CI 预检 (含 unit/integration/property smoke)
	$(MAKE) ci-check
	@echo "🧪 运行 CI 测试套件..."
	$(TEST_ENV) $(PYTEST) tests/ci/unit/ -q $(ARGS)
	$(TEST_ENV) $(PYTEST) tests/ci/integration/ -q $(ARGS)
	$(TEST_ENV) HYPOTHESIS_PROFILE=default $(PYTEST) tests/ci/property/ -q $(ARGS)

.PHONY: help install run test migrate shell lint clean ci-check ci-check-full qcluster-dev redis-cli redis-status redis-reset

# 默认 Python 和虚拟环境
VENV_DIR ?= .venv
UV := uv
PYTHON := $(VENV_DIR)/bin/python
PYTEST := $(VENV_DIR)/bin/pytest
MANAGE := $(PYTHON) apiSystem/manage.py
UVICORN := $(VENV_DIR)/bin/uvicorn
WATCHFILES := $(VENV_DIR)/bin/watchfiles
PORT ?= 8002
RUN_DEV_FORCE_POLLING ?= true
RUN_DEV_POLL_DELAY_MS ?= 300
QCLUSTER_DEV_FORCE_POLLING ?= true
QCLUSTER_DEV_POLL_DELAY_MS ?= 300
QCLUSTER_WATCH_PATHS ?= apps apiSystem

# 数据库配置（默认 PostgreSQL，可通过 DB_ENGINE=sqlite 切换）
DB_ENGINE ?= postgresql
DATABASE_PATH ?=
DB_NAME ?= fachuan_dev
DB_USER ?= postgres
DB_PASSWORD ?= postgres
DB_HOST ?= 127.0.0.1
DB_PORT ?= 5432

# 测试数据库配置
TEST_DB_ENGINE ?= postgresql
TEST_DB_PATH ?= /tmp/fachuan_pytest.sqlite3
TEST_DB_NAME ?= fachuan_test
TEST_DB_USER ?= postgres
TEST_DB_PASSWORD ?= postgres
TEST_DB_HOST ?= 127.0.0.1
TEST_DB_PORT ?= 5432

export DB_ENGINE DATABASE_PATH DB_NAME DB_USER DB_PASSWORD DB_HOST DB_PORT

# 颜色定义
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

TEST_ENV = DJANGO_DEBUG=1 DB_ENGINE=$(TEST_DB_ENGINE) DATABASE_PATH=$(TEST_DB_PATH) DB_NAME=$(TEST_DB_NAME) DB_USER=$(TEST_DB_USER) DB_PASSWORD=$(TEST_DB_PASSWORD) DB_HOST=$(TEST_DB_HOST) DB_PORT=$(TEST_DB_PORT) PYTHONPATH=apiSystem:.

help: ## 显示帮助信息
	@echo "$(GREEN)法律事务管理系统 - Backend$(NC)"
	@echo ""
	@echo "可用命令:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'

# ============================================================
# 安装和配置
# ============================================================

install: ## 安装生产依赖
	$(UV) sync --no-dev

install-dev: ## 安装全部依赖（含 dev + test）
	$(UV) sync

venv: ## 创建虚拟环境
	$(UV) venv $(VENV_DIR) --python 3.12
	@echo "$(GREEN)虚拟环境已创建，请运行: source $(VENV_DIR)/bin/activate$(NC)"

# ============================================================
# 开发服务器
# ============================================================

run: migrate ## 启动开发服务器 (默认端口 8002, 使用 uvicorn, 可通过 PORT=8003 修改)
	cd apiSystem && ../$(UVICORN) apiSystem.asgi:application --host 0.0.0.0 --port $(PORT)

run-dev: migrate ## 启动开发服务器 (热重载稳定模式：默认启用 polling，避免与 qcluster 并行时卡住)
	cd apiSystem && WATCHFILES_FORCE_POLLING=$(RUN_DEV_FORCE_POLLING) WATCHFILES_POLL_DELAY_MS=$(RUN_DEV_POLL_DELAY_MS) ../$(UVICORN) apiSystem.asgi:application --host 0.0.0.0 --port $(PORT) --reload --reload-delay 0.5 --reload-dir ../apps --reload-dir . --reload-include '*.html'

run-port: migrate ## 启动开发服务器 (自定义端口, 使用 PORT=8001)
	cd apiSystem && ../$(UVICORN) apiSystem.asgi:application --host 0.0.0.0 --port $(PORT)

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
	@if [ "$(DB_ENGINE)" = "sqlite" ]; then \
		rm -f apiSystem/db.sqlite3; \
		$(MANAGE) migrate; \
	elif [ "$(DB_ENGINE)" = "postgresql" ]; then \
		$(MANAGE) flush --noinput; \
		$(MANAGE) migrate; \
	else \
		echo "$(YELLOW)未知 DB_ENGINE=$(DB_ENGINE)，使用 flush + migrate 兜底$(NC)"; \
		$(MANAGE) flush --noinput; \
		$(MANAGE) migrate; \
	fi
	@echo "$(GREEN)数据库已重置 (DB_ENGINE=$(DB_ENGINE))$(NC)"

# ============================================================
# 用户管理
# ============================================================

superuser: ## 创建超级用户
	$(MANAGE) createsuperuser

# ============================================================
# 测试
# ============================================================

test: ## 运行测试
	$(TEST_ENV) $(PYTEST) tests/ci -v --tb=short $(ARGS)

test-cov: ## 运行测试 (带覆盖率)
	$(TEST_ENV) $(PYTEST) tests/ci -v --tb=short --cov=apps --cov-report=html --cov-report=term

test-fast: ## 快速测试 (不显示详情)
	$(TEST_ENV) $(PYTEST) tests/ci -q

test-unit: ## 运行单元测试
	$(TEST_ENV) $(PYTEST) tests/ci/unit -v --tb=short $(ARGS)

test-integration: ## 运行集成测试
	$(TEST_ENV) $(PYTEST) tests/ci/integration -v --tb=short $(ARGS)

test-property: ## 运行 Property-Based Tests
	$(TEST_ENV) $(PYTEST) tests/ci/property -v --tb=short $(ARGS)

test-structure: ## 运行结构验证测试
	$(TEST_ENV) $(PYTEST) tests/ci/structure -v --tb=short --no-cov $(ARGS)

test-admin: ## 运行 Admin 测试
	$(TEST_ENV) $(PYTEST) tests/ci/unit -v --tb=short -k "admin" $(ARGS)

# ============================================================
# 代码质量
# ============================================================

RUFF_RATCHET_PATHS = \
	apps/core/security/scrub.py \
	apps/core/infrastructure/cache.py \
	apps/automation/models/token.py \
	apps/automation/services/automation_service_adapter.py \
	apps/automation/services/scraper/core/token_service.py \
	apps/automation/services/token/cache_manager.py \
	apps/automation/services/token/history_recorder.py \
	apps/automation/services/token/token_acquisition_orchestrator.py \
	apps/automation/services/token/trigger_reasons.py \
	apps/client/services/wiring.py \
	apps/chat_records/services/wiring.py \
	apps/core/services/wiring.py \
	apps/core/services/conversation_service.py \
	apps/core/services/cause_court_initialization_service.py \
	apps/core/services/court_tokens/baoquan_token_service.py \
	apps/litigation_ai/services/wiring.py \
	apps/litigation_ai/agent/factory.py \
	apps/litigation_ai/agent/llm_provider.py \
	apps/litigation_ai/agent/middleware.py \
	apps/litigation_ai/chains/document_type_parse_chain.py \
	apps/litigation_ai/chains/litigation_draft_chain.py \
	apps/litigation_ai/chains/litigation_goal_intake_chain.py \
	apps/litigation_ai/chains/user_choice_parse_chain.py

lint-ratchet: ## 代码检查（仅棘轮路径）
	$(PYTHON) -m ruff check $(RUFF_RATCHET_PATHS) --config ruff.toml

lint: ## 全量代码检查 apps/
	$(PYTHON) -m ruff check apps --config ruff.toml

lint-full: lint ## 全量代码检查（lint 别名）

format: ## 格式化代码
	$(PYTHON) -m black apps --line-length=120
	$(PYTHON) -m isort apps

typecheck-ratchet: ## 类型检查（仅棘轮路径）
	PYTHONPATH=apiSystem:. $(PYTHON) -m mypy \
		apps/core/infrastructure/throttling.py \
		apps/core/middleware_request_id.py \
		apps/core/exceptions_handlers.py \
		apps/core/httpx_clients.py \
		apps/core/config/django_runtime.py \
		apps/core/protocols/common_protocols.py \
		apps/core/dto/auth.py \
		apps/core/llm/config.py \
		apps/core/llm/service.py \
		apps/core/llm/router.py \
		apps/core/llm/backends/base.py \
		apps/core/services/wiring.py \
		apps/core/services/system_config_service.py \
		apps/core/security/secret_codec.py \
		apps/core/dependencies/automation_sms.py \
		apps/core/security/scrub.py \
		apps/automation/services/document/document_processing_service_adapter.py \
		apps/automation/services/token/trigger_reasons.py \
		apps/automation/services/scraper/core/token_service.py \
		apps/cases/services/case/case_service.py \
		apps/contracts/services/contract/contract_service_adapter.py \
		apps/organization/services/org_access_computation_service.py \
		apps/organization/services/wiring.py \
		--follow-imports=silent \
		--config-file mypy.ini

typecheck: ## 全量类型检查 apps/
	PYTHONPATH=apiSystem:. $(PYTHON) -m mypy apps --config-file mypy.ini

typecheck-full: typecheck ## 全量类型检查（typecheck 别名）

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

qcluster: migrate ## 启动 Django-Q 任务队列（与 Django Web 启动顺序不限）
	@pkill -9 -f 'python.*manage.py qcluster' 2>/dev/null || true
	@sleep 1
	$(MANAGE) qcluster

qcluster-start: migrate ## 启动 Django-Q 并处理待处理任务（与 Django Web 启动顺序不限）
	@pkill -9 -f 'python.*manage.py qcluster' 2>/dev/null || true
	@sleep 1
	$(MANAGE) process_pending_tasks --reset
	$(MANAGE) qcluster

qcluster-dev: migrate ## 启动 Django-Q（文件变化自动重启）
	@echo "$(GREEN)启动 qcluster-dev: 检测 Python 文件变化后自动重启 qcluster$(NC)"
	@echo "$(YELLOW)监听目录: $(QCLUSTER_WATCH_PATHS)$(NC)"
	@WATCHFILES_FORCE_POLLING=$(QCLUSTER_DEV_FORCE_POLLING) WATCHFILES_POLL_DELAY_MS=$(QCLUSTER_DEV_POLL_DELAY_MS) $(WATCHFILES) --target-type command --filter python --ignore-paths ".venv,node_modules,.git,__pycache__,media,staticfiles,logs,htmlcov,.pytest_cache" "$(MANAGE) qcluster" $(QCLUSTER_WATCH_PATHS)

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
# Redis（本地开发需要 Redis 时使用）
# ============================================================

REDIS_HOST ?= 127.0.0.1
REDIS_PORT ?= 6379

redis-cli: ## 连接 Redis CLI
	redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT)

redis-status: ## 检查 Redis 连通性和信息
	@redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) ping 2>/dev/null && echo "Redis OK" || echo "Redis 不可达"
	@redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) info memory 2>/dev/null | grep used_memory_human || true

redis-reset: ## 清除 Redis 中本项目的缓存键（仅开发用！）
	@echo "$(YELLOW)警告: 这将清除 lawfirm:* 前缀的所有缓存键$(NC)"
	@read -p "确认继续? [y/N] " confirm && [ "$$confirm" = "y" ]
	redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --scan --pattern "lawfirm:*" | xargs -r redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) del
	@echo "$(GREEN)lawfirm:* 缓存键已清除$(NC)"

# ============================================================
# 健康检查
# ============================================================

health: ## 检查服务健康状态
	@curl -sf http://localhost:$(PORT)/health/ && echo " OK" || echo "服务未运行"

health-detail: ## 详细健康检查
	@curl -sf http://localhost:$(PORT)/health/ && echo " OK (db connected)" || echo "服务未运行或数据库不可用"

# ============================================================
# 国际化 (i18n)
# ============================================================

messages: ## 提取翻译字符串，生成 .po 文件
	cd apiSystem && ../$(PYTHON) manage.py makemessages -l en -l zh_Hans --ignore='.venv/*' --ignore='venv312/*'

compilemessages: ## 编译 .po 为 .mo 文件
	cd apiSystem && ../$(PYTHON) manage.py compilemessages
