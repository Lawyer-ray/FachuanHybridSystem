# Enterprise Data（MCP）使用说明

## 已接入能力

- Provider 抽象：`tianyancha`（已接入）、`qichacha`（骨架预留）
- 协议策略：优先 `streamable_http`，失败自动回退 `sse`
- 标准化能力：
  - `search_companies`
  - `get_company_profile`（映射 `get_company_info`）
  - `get_company_risks`
  - `get_company_shareholders`
  - `get_company_personnel`
  - `get_person_profile`
  - `search_bidding_info`

## 后端 API

统一入口：`/api/v1/enterprise-data/*`

- `GET /providers`
- `GET /companies/search`
- `GET /companies/profile`
- `GET /companies/risks`
- `GET /companies/shareholders`
- `GET /companies/personnel`
- `GET /persons/profile`
- `GET /bidding/search`

统一响应骨架：

```json
{
  "query": {},
  "data": {},
  "meta": {
    "provider": "tianyancha",
    "tool": "search_companies",
    "transport": "sse",
    "requested_transport": "streamable_http",
    "fallback_used": true,
    "cached": false,
    "observability": {
      "window_seconds": 300,
      "total": 20,
      "success_rate": 0.95,
      "fallback_rate": 0.25,
      "avg_duration_ms": 1280
    }
  },
  "raw": null
}
```

## Admin 工作台

路径：`/admin/enterprise_data/mcpworkbench/`

- 仅超级管理员可访问（页面权限 + 服务端权限双重校验）
- 可查看工具列表、参数 schema、最近样例
- 可执行调试、查看执行历史并一键重放
- 执行结果已做敏感字段脱敏

## 关键配置项（SystemConfig）

- 基础：
  - `ENTERPRISE_DATA_DEFAULT_PROVIDER`
  - `ENTERPRISE_DATA_CACHE_TTL_SECONDS`
- 天眼查：
  - `TIANYANCHA_MCP_ENABLED`
  - `TIANYANCHA_MCP_TRANSPORT`
  - `TIANYANCHA_MCP_BASE_URL`
  - `TIANYANCHA_MCP_SSE_URL`
  - `TIANYANCHA_MCP_API_KEY`
  - `TIANYANCHA_MCP_TIMEOUT_SECONDS`
- 限流/重试：
  - `ENTERPRISE_DATA_RATE_LIMIT_REQUESTS`
  - `ENTERPRISE_DATA_RATE_LIMIT_WINDOW_SECONDS`
  - `ENTERPRISE_DATA_RETRY_MAX_ATTEMPTS`
  - `ENTERPRISE_DATA_RETRY_BACKOFF_SECONDS`
- 可观测告警：
  - `ENTERPRISE_DATA_METRICS_WINDOW_SECONDS`
  - `ENTERPRISE_DATA_ALERT_MIN_SAMPLES`
  - `ENTERPRISE_DATA_ALERT_SUCCESS_RATE_THRESHOLD`
  - `ENTERPRISE_DATA_ALERT_FALLBACK_RATE_THRESHOLD`
  - `ENTERPRISE_DATA_ALERT_AVG_LATENCY_MS_THRESHOLD`
- 企查查预留：
  - `QICHACHA_MCP_ENABLED`
  - `QICHACHA_MCP_TRANSPORT`
  - `QICHACHA_MCP_BASE_URL`
  - `QICHACHA_MCP_SSE_URL`
  - `QICHACHA_MCP_API_KEY`
  - `QICHACHA_MCP_TIMEOUT_SECONDS`

## 运行注意事项

- `is_secret=True` 的配置需要稳定的 `CREDENTIAL_ENCRYPTION_KEY`。  
  开发环境若每次进程启动都随机生成密钥，密文将无法跨进程解密。
