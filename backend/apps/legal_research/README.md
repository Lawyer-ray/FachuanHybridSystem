# 🔍 案例检索（legal_research）

面向「威科先行（WKInfo）」的类案检索引擎：任务编排、多路查询召回、LLM 相似度评分、PDF 落盘与 Agent 化检索能力输出（MCP）。

## 功能概述

- 任务式检索：创建任务 → Django-Q 异步执行（扫描候选 → 详情抓取 → 相似度评分 → 命中落库并下载 PDF）
- 检索策略：主查询 / LLM 变体查询 / 反馈查询三路召回，NLP 意图要素抽取（关系/违约/损害/救济），自适应阈值衰减与双模型交叉审查
- 相似度：多维召回打分（keyword/summary/BM25/vector/passage/metadata 加权，权重经 SystemConfig 可调）+ LLM 结构化评分 + 可选交叉编码器 rerank（`/v1/rerank`）
- **双通道数据源**：优先私有 HTTP API（`plugins.weike_api_private`，懒加载探测），失败回退 Playwright 浏览器登录/抓取；API 连续失败自动降级冷却（streak 阈值/冷却秒数可配）
- 检索事件审计（每次接口调用、状态码、耗时，敏感字段脱敏）+ 人工反馈在线微调（写回 SystemConfig 调权）
- Agent/MCP 能力层：`/capability/search` 输出 v1 契约（intent/court_scope/year_range/budget、snippets、subscores、decision、query_trace），并被 `backend/mcp_server` 注册为 MCP tool
- 案例批量下载（按案号列表下载 PDF/Word，Admin 打包 zip）与法规引用核查端点（依赖 `plugins.law_verification_wps`）

## 目录结构

```
legal_research/
├── apps.py / tasks.py / signals.py    # Q 任务入口（防 ORM 连接泄漏）/ post_delete 清 PDF
├── models/                            # task / result / task_event / case_download
├── api/legal_research_api.py          # 全部端点
├── schemas/legal_research_schemas.py  # 含 Agent v1 契约全套
├── admin/                             # task / result / case_download 三套 Admin
├── services/
│   ├── sources/                       # CaseSourceClient Protocol + factory + weike/ 客户端
│   ├── task/                          # service / executor（主编排）/ 下载 / 事件 / 反馈 / 状态回填
│   ├── executor_components/           # 9 个 Mixin（cache/feedback/intent/policy/query/...）
│   ├── similarity/                    # 评分编排 / 打分原语 / 段落选择 / 两级缓存 / reranker / 调参
│   ├── capability/                    # Agent v1 检索编排 + MCP 轻量封装
│   ├── keywords.py / llm_preflight.py
├── management/commands/benchmark_legal_research_retrieval.py  # 回放标注样本输出 P/R/F1
├── evaluation/                        # 标注样本与基线报告
└── migrations/                        # 0001–0013
```

## 数据模型

- `LegalResearchTask` — 检索任务（关键词/高级检索 JSON/法院与案由筛选/目标数/阈值/LLM 后端与并发/进度）
- `LegalResearchResult` — 命中结果（rank、法院、案号、摘要、相似度、PDF、metadata）
- `LegalResearchTaskEvent` — 检索事件审计
- `CaseDownloadTask` / `CaseDownloadResult` — 案例批量下载

## API 端点

前缀 `/api/v1/legal-research`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks` | 创建检索任务 |
| GET | `/tasks/{id}` | 任务状态（含队列失败回填） |
| GET | `/tasks/{id}/results` | 命中列表 |
| GET | `/tasks/{id}/results/{rid}/download`、`/results/download` | 单个 / 打包 zip 下载（限流 EXPORT） |
| POST | `/capability/search`、`/capability/search/mcp` | Agent v1 检索（支持 Idempotency-Key 幂等） |
| POST | `/law-verification/check` | 文档法规引用核查 |

## Admin

- `LegalResearchTaskAdmin`：私有 API 阶段指标/时间线/接口返回可视化（插件可用时）、取消任务按钮；列表按律所隔离
- `LegalResearchResultAdmin`：人工反馈（标记真实命中/误命中 → 在线微调）
- `CaseDownloadTaskAdmin`：打包下载 / 重试失败项 action；列表按律所隔离（产物落 `legal_research/case_download/` 下 media 相对路径，zip 经系统临时目录打包）

## 异步任务与信号

- Q 任务 `execute_legal_research_task`、`execute_case_download_task`（ThreadPoolExecutor max_workers=1 + close_old_connections）
- signal：post_delete 清理结果 PDF 物理文件；无定时任务

## 设计要点

- 「私有 API 优先、Playwright 兜底」双通道 + 降级冷却是核心可靠性设计
- 调参全部集中在 `LegalResearchTuningConfig`（SystemConfig key 读写）
- 评测基线数据集 + benchmark 命令构成回归闭环

## 外部集成

威科先行 wkinfo.com.cn、LLM（apps.core 统一后端）、Reranker HTTP 端点、Playwright（apps.core.services.browser）、plugins.weike_api_private / law_verification_wps、backend/mcp_server

## 依赖模块

- `apps.core`、`apps.organization`（AccountCredential）、plugins 三包
