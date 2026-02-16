# 安全与运维基线

## 鉴权策略
- API 默认使用 `Authorization: Bearer <JWT>`（前端）或 Django Session（Admin/AJAX）。  
- `auth=None` 仅允许用于注册接口；其他接口禁止匿名访问。

## CORS / CSRF
- 默认采用 origins 白名单，不允许 `CORS_ALLOW_ALL_ORIGINS`。  
- `CORS_ALLOW_CREDENTIALS` 默认关闭；只有确需跨域 Cookie 才显式开启，并确保 `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` 严格白名单。
- `DJANGO_ALLOW_LAN=True` 仅用于开发联调：必须显式配置 `DJANGO_LAN_ALLOWED_HOSTS`、`CORS_ALLOWED_ORIGINS`、`CSRF_TRUSTED_ORIGINS`，生产环境禁止开启。

## Cookie 安全（生产建议）
- 默认开启 `SESSION_COOKIE_HTTPONLY`、`CSRF_COOKIE_HTTPONLY`。  
- 默认 `SESSION_COOKIE_SAMESITE=Lax`、`CSRF_COOKIE_SAMESITE=Lax`，按业务需要调整。  
- 反代部署如需信任 `X-Forwarded-Proto`，设置 `DJANGO_SECURE_PROXY_SSL_HEADER=True`。
- 反代部署如需信任 `X-Forwarded-Host`，设置 `USE_X_FORWARDED_HOST=True`（仅建议在边界反代可信、且已锁定 `ALLOWED_HOSTS` 时开启）。

## 安全响应头（生产建议）
- 默认启用 CSP 的 Report-Only（不拦截，仅用于观测与逐步收敛）。
  - `CONTENT_SECURITY_POLICY_REPORT_ONLY`：设置后将返回 `Content-Security-Policy-Report-Only`。
  - `CONTENT_SECURITY_POLICY`：设置后将返回强制的 `Content-Security-Policy`（需要确认 Admin 页面脚本策略）。
- COOP/CORP/COEP（按部署需求调整）：
  - `CROSS_ORIGIN_OPENER_POLICY`（默认 `same-origin`）
  - `CROSS_ORIGIN_RESOURCE_POLICY`（默认 `same-origin`）
  - `CROSS_ORIGIN_EMBEDDER_POLICY`（默认 `unsafe-none`）

## 限流与缓存
- 限流基于 Django cache，采用按窗口分桶的原子计数；关键端点（登录、LLM/OCR、上传、导出、任务提交）均需限流保护。  
- 开发默认 `LocMemCache`；生产建议配置 `DJANGO_CACHE_REDIS_URL` 使用 Redis cache，以保证多进程/多副本下限流一致。

## Metrics / 观测
- 请求与外呼指标默认在生产开启（可通过 env 控制）：  
  - `DJANGO_REQUEST_METRICS`：请求级 metrics（默认生产开启）  
  - `DJANGO_HTTPX_METRICS`：httpx 外呼 metrics（默认关闭，需要显式开启）  
- 管理员可访问的 metrics 端点（均带鉴权与限流）：  
  - `/api/v1/resource/metrics?window_minutes=10&top=10`：JSON 快照（含 Top 慢/Top 错）  
  - `/api/v1/resource/metrics/prometheus?window_minutes=10`：Prometheus 文本快照

## Channels / WebSocket
- 未配置时使用 InMemory channel layer，仅适合单进程本地开发。  
- 生产建议配置 `DJANGO_CHANNEL_REDIS_URL` 启用 Redis channel layer。

## 健康检查端点
- `/api/v1/health/live`、`/api/v1/health/ready`：面向探针，可保持开放。  
- `/api/v1/health/detail`：仅管理员可访问，避免敏感诊断信息对外暴露。
