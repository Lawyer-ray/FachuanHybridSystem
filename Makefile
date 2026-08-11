# 法穿AI Copilot - 根目录 Makefile
# ============================================================
# 本地 CI 入口，调用 scripts/ci-local.sh
# ============================================================

GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m

ci: ## 快速本地 CI（不需要数据库：ruff + mypy + tsc + eslint + build + bandit + pip-audit）
	@bash scripts/ci-local.sh --quick

ci-full: ## 完整本地 CI（需要 PostgreSQL：ci + 测试 + 覆盖率 + smoke check）
	@bash scripts/ci-local.sh --full

ci-backend: ## 仅后端 CI（快速模式）
	@bash scripts/ci-local.sh --quick --backend

ci-frontend: ## 仅前端 CI（tsc + eslint + build）
	@bash scripts/ci-local.sh --quick --frontend

ci-backend-full: ## 仅后端 CI（完整模式，需要 PostgreSQL）
	@bash scripts/ci-local.sh --full --backend

# ============================================================
# 开发服务器（前台运行，可直接 Ctrl+C 退出）
# ============================================================

frontend: ## 启动前端开发服务器（Vite，热重载，端口 5173）
	cd frontend && pnpm dev

backend: ## 启动后端开发服务器（Uvicorn，热重载，默认端口 8002，可用 PORT=8003 覆盖）
	cd backend && $(MAKE) run-dev

q: ## 启动 Django-Q 任务队列（文件变化自动重启）
	cd backend && $(MAKE) qcluster-dev

install-hooks: ## 安装 git pre-push hook（推送前自动运行本地 CI）
	@ln -sf ../../scripts/pre-push .git/hooks/pre-push
	@chmod +x scripts/pre-push
	@echo "$(GREEN)✓ pre-push hook 已安装$(NC)"
	@echo "  推送时将自动运行 'make ci'，失败则阻止推送。"
	@echo "  跳过: git push --no-verify"

help: ## 显示帮助信息
	@echo "$(GREEN)法穿AI Copilot - 本地 CI$(NC)"
	@echo ""
	@echo "可用命令:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "远端 CI 对照表:"
	@echo "  ci          → backend-security-guard, backend-ruff-full, backend-mypy-curated, frontend"
	@echo "  ci-full     → 上述 + backend-unit, backend-integration, backend-property, coverage"
	@echo ""
	@echo "推送前建议:  make ci-full"
	@echo "日常开发:    make ci"
	@echo "安装 hook:   make install-hooks"
	@echo "启动服务:    make frontend / make backend / make q"

.PHONY: help ci ci-full ci-backend ci-frontend ci-backend-full install-hooks frontend backend q
