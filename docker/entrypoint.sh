#!/bin/bash
# ============================================================
# 法穿案件管理系统 - Docker 入口脚本
# ============================================================
# 功能：
# - 显示版本信息
# - 等待依赖服务就绪
# - 运行数据库迁移
# - 收集静态文件（生产环境）
# - 初始化系统配置
# - 支持幂等执行（多次运行安全）
# ============================================================
# Requirements: 7.1, 7.2, 7.4, 7.5, 13.2

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_debug() {
    if [ "$DJANGO_DEBUG" = "True" ] || [ "$DJANGO_DEBUG" = "true" ]; then
        echo -e "${BLUE}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
    fi
}

# 显示启动信息
show_banner() {
    echo "=========================================="
    echo "  法穿案件管理系统 Docker 启动"
    echo "  版本: ${APP_VERSION:-1.0.0}"
    echo "  环境: $([ "$DJANGO_DEBUG" = "True" ] || [ "$DJANGO_DEBUG" = "true" ] && echo '开发模式' || echo '生产模式')"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="
}

# 等待 Redis 就绪
wait_for_redis() {
    if [ -n "$REDIS_URL" ]; then
        log_info "等待 Redis 连接..."
        # 从 REDIS_URL 提取主机和端口
        # 支持格式: redis://host:port/db 或 redis://host:port
        REDIS_HOST=$(echo "$REDIS_URL" | sed -E 's|redis://([^:]+):([0-9]+).*|\1|')
        REDIS_PORT=$(echo "$REDIS_URL" | sed -E 's|redis://([^:]+):([0-9]+).*|\2|')
        
        # 默认值
        REDIS_HOST=${REDIS_HOST:-redis}
        REDIS_PORT=${REDIS_PORT:-6379}
        
        MAX_RETRIES=30
        RETRY_COUNT=0
        
        log_debug "Redis 连接信息: $REDIS_HOST:$REDIS_PORT"
        
        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
                log_info "Redis 已就绪 ($REDIS_HOST:$REDIS_PORT)"
                return 0
            fi
            RETRY_COUNT=$((RETRY_COUNT + 1))
            log_warn "等待 Redis... ($RETRY_COUNT/$MAX_RETRIES)"
            sleep 1
        done
        
        log_error "Redis 连接超时，请检查 Redis 服务是否正常运行"
        return 1
    else
        log_warn "未配置 REDIS_URL，跳过 Redis 检查"
    fi
}

# 确保数据目录存在
ensure_directories() {
    log_info "检查数据目录..."
    
    # 创建必要的目录
    mkdir -p /app/data 2>/dev/null || true
    mkdir -p /app/media 2>/dev/null || true
    mkdir -p /app/logs 2>/dev/null || true
    
    log_debug "数据目录检查完成"
}

# 运行数据库迁移（幂等操作）
run_migrations() {
    log_info "运行数据库迁移..."
    cd /app/apiSystem
    
    if python manage.py migrate --noinput; then
        log_info "数据库迁移完成"
    else
        log_error "数据库迁移失败"
        log_error "请检查数据库配置和迁移文件"
        exit 1
    fi
}

# 收集静态文件（仅生产环境）
collect_static() {
    if [ "$DJANGO_DEBUG" != "True" ] && [ "$DJANGO_DEBUG" != "true" ]; then
        log_info "收集静态文件..."
        cd /app/apiSystem
        
        if python manage.py collectstatic --noinput; then
            log_info "静态文件收集完成"
        else
            log_warn "静态文件收集失败，继续启动..."
        fi
    else
        log_debug "开发模式，跳过静态文件收集"
    fi
}

# 初始化系统配置（幂等操作）
init_system_config() {
    log_info "初始化系统配置..."
    cd /app/apiSystem
    
    # --skip-existing 确保幂等性：已存在的配置不会被覆盖
    if python manage.py init_system_config --skip-existing 2>/dev/null; then
        log_info "系统配置初始化完成"
    else
        log_debug "系统配置初始化跳过（可能已存在或命令不可用）"
    fi
}

# 验证环境配置
validate_environment() {
    log_info "验证环境配置..."
    
    # 生产环境必须设置 SECRET_KEY
    if [ "$DJANGO_DEBUG" != "True" ] && [ "$DJANGO_DEBUG" != "true" ]; then
        # 检查是否使用了不安全的默认密钥
        UNSAFE_KEYS="change-me-in-production change-me-in-production-use-generated-key django-insecure-dev-only-do-not-use-in-production"
        
        if [ -z "$DJANGO_SECRET_KEY" ]; then
            log_error "生产环境必须设置 DJANGO_SECRET_KEY"
            log_error "请在 .env 文件中配置安全的密钥"
            log_error "生成命令: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
            exit 1
        fi
        
        for unsafe_key in $UNSAFE_KEYS; do
            if [ "$DJANGO_SECRET_KEY" = "$unsafe_key" ]; then
                log_error "生产环境不能使用默认的不安全密钥: $unsafe_key"
                log_error "请生成一个新的安全密钥"
                log_error "生成命令: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
                exit 1
            fi
        done
        
        log_info "SECRET_KEY 验证通过"
    fi
    
    # 检查数据库路径
    if [ -n "$DATABASE_PATH" ]; then
        DB_DIR=$(dirname "$DATABASE_PATH")
        if [ ! -d "$DB_DIR" ]; then
            log_warn "数据库目录不存在，正在创建: $DB_DIR"
            mkdir -p "$DB_DIR" 2>/dev/null || true
        fi
        log_debug "数据库路径: $DATABASE_PATH"
    fi
    
    log_info "环境配置验证通过"
}

# 主流程
main() {
    # 显示启动信息
    show_banner
    
    # 验证环境
    validate_environment
    
    # 确保目录存在
    ensure_directories
    
    # 等待依赖服务
    wait_for_redis
    
    # 切换到应用目录
    cd /app/apiSystem
    
    # 运行迁移（幂等）
    run_migrations
    
    # 收集静态文件
    collect_static
    
    # 初始化配置（幂等）
    init_system_config
    
    log_info "启动应用服务..."
    echo "=========================================="
    
    # 执行传入的命令
    exec "$@"
}

# 运行主流程
main "$@"
