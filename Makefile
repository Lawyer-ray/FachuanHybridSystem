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

.PHONY: help ci ci-full ci-backend ci-frontend ci-backend-full
