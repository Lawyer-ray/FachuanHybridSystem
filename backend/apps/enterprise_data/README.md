# 🏭 企业数据查询（enterprise_data）

企业数据查询统一网关：以 MCP 协议接入天眼查 / 企查查，输出标准化企业画像 / 风险 / 股东 / 高管 / 招投标查询与 Admin 调试工作台。

## 功能概述

- **双 provider**：`tianyancha`（默认，streamable_http 优先失败回退 SSE）与 `qichacha`（6 个独立 MCP Server：company / risk / ipr / operation / executive / history，能力路由表映射统一能力）
- 统一响应协议 `{query, data, meta, raw}`，meta 含 transport 回退、API Key 池切换、observability 窗口指标
- **API Key 池**（McpApiKeyPool）：多 key（SystemConfig 或环境变量，支持 `*_API_KEYS` 复数变量），成功 key 置偏好（30 天）、鉴权失败熔断 1h、限流熔断 2min，指纹化缓存
- **弹性**：Django cache 结果缓存 + 失败时返回过期缓存（stale fallback，meta 标 `stale:true`）；transport 不健康隔离 10 分钟；进程级持久事件循环复用（`_get_or_create_loop`）；同步 + 异步双套 API
- **指标与告警**：按窗口聚合成功率 / 回退率 / 平均耗时，超阈值去重告警日志
- **Admin MCP 调试工作台**：工具列表 + 参数 schema + 最近样例、执行调试、历史记录一键重放；响应经 `scrub_for_storage` 脱敏、JSON 超 50KB 截断

## 目录结构

```
enterprise_data/
├── models/workbench.py            # McpWorkbench（unmanaged 占位）+ McpWorkbenchExecution（执行历史）
├── api/enterprise_data_api.py     # 全 async 端点
├── schemas/ + services/
│   ├── enterprise_data_service.py # 统一查询编排 + 缓存 + stale 回退
│   ├── provider_registry.py       # 配置读取与实例化
│   ├── metrics_service.py
│   ├── clients/                   # mcp_tool_client（限流/重试/transport 回退/key failover）、api_key_pool
│   └── providers/                 # base Protocol、tianyancha_mcp、qichacha_mcp + adapters/ 响应归一化
└── templates/admin/enterprise_data/mcp_workbench/
```

## 数据模型

- `McpWorkbench` — unmanaged 占位模型（挂 Admin 页）
- `McpWorkbenchExecution` — 执行历史（参数 / 响应 / 元信息、成功标志、错误码、耗时、协议、操作人、replay_of 自引用）

## API 端点

前缀 `/api/v1/enterprise-data`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/providers` | provider 列表（include_tools 可探测工具） |
| GET | `/companies/search?keyword=` | 企业搜索 |
| GET | `/companies/{company_id}` | 企业画像 |
| GET | `/companies/{company_id}/risks?risk_type=` | 风险（自身/周边/预警/历史） |
| GET | `/companies/{company_id}/shareholders`、`/personnel` | 股东 / 高管 |
| GET | `/personnel/{hcgid}` | 人员画像 |
| GET | `/biddings/search?keyword=&search_type=&bid_type=&start_date=&end_date=` | 招投标 |

## 关键配置

- 天眼查：`TIANYANCHA_MCP_TRANSPORT`、`TIANYANCHA_MCP_BASE_URL` / `_SSE_URL`、`TIANYANCHA_MCP_API_KEY`（多 key 走 `TIANYANCHA_MCP_API_KEYS`）
- 企查查：`QCC_MCP_BASE_URL`、`QCC_MCP_API_KEY`（含复数 `QCC_MCP_API_KEYS`）
- 限流 / 重试 / 指标窗口 / 告警阈值 / 缓存 TTL 当前在 `provider_registry.py` 中以常量返回

## 运行注意事项

- `is_secret=True` 的配置需要稳定的 `CREDENTIAL_ENCRYPTION_KEY`——开发环境若每次进程启动随机生成密钥，密文将无法跨进程解密
