# ⚙️ 核心模块（core）

全系统基础设施层：统一配置管理、统一异常体系、Protocol 接口 + DTO + ServiceLocator 依赖注入中枢、认证/权限、限流、加密、LLM 平台、全局搜索、仪表盘、任务队列（Django-Q/Redis）、遥测、健康检查、文件系统（上传路径 / 文件夹绑定）、公共浏览器服务与 Admin 工具。

> **拆分历史**：云存储已拆分为独立 app `apps/cloud_storage`（表名钉死 `core_cloudstorageaccount`，2026-09 #459）；core 侧仅遗留 cloud_storage 的 admin 模板目录。

## 功能概述

- **配置管理**（config/）：schema 注册表 + env/yaml providers，`get_config_manager()` / `get_config_value()` 等导出
- **统一异常体系**（exceptions/）：BusinessError 族 + chat 族 + external 族 + 全局异常处理器与错误目录
- **依赖注入中枢**：`ServiceLocator`（infrastructure/ + 6 个 mixin + interfaces 统一出口）与 `dependencies/` 下 20 个 `build_*_service` 工厂
- **LLM 平台**（llm/）：多 backend 注册、多 Key 池（key_pool）、熔断（circuit_breaker）、降级（fallback_policy）、结构化输出、追踪（LLMCallRecord）、预热；`/api/v1/llm` 端点组
- **任务队列**（tasking/）：Django-Q/Redis 封装（submission / scheduler / redis_queue / qcluster_spawn / cleanup）+ `/api/v1/task-queue` API + RedisQueueTool Admin
- **遥测**（telemetry/ + infrastructure/monitoring）：请求 / HTTPx / 缓存命中率指标、直方图分位、Prometheus 文本导出（`/api/v1/resource/metrics[/prometheus]`）
- **文件系统**（filesystem/）：`upload_paths.py` 路径工厂（DatedUUIDPath / EntityIdPath 等 + MediaEntity 注册表，**禁止手拼路径**）、文件夹绑定基类与 CRUD、InodeResolver、路径校验
- **公共浏览器服务**（services/browser/）：create_browser / create_browser_async、Profile 体系、CDP 连接器、反检测、Chrome 进程管理（**禁止直接用 sync_playwright**）
- **安全**（security/）：JWTOrSessionAuth、admin_access、permissions、日志脱敏 scrub、secret_codec、model_fields/encrypted
- **中间件**：RequestId、SecurityHeaders、PermissionsPolicy、ServiceLocatorScope、TokenRateLimit（settings 装配）
- 全局搜索 `/api/v1/search`（PostgreSQL 全文检索）、仪表盘 `/api/v1/dashboard/stats`
- 一张网担保 Token 服务（services/court_tokens）、PDF 合并 / 工具、LibreOffice 定位、mac 剪贴板、种子数据

## 目录结构

```
core/
├── api/            # system-configs CRUD、search、dashboard、task_queue、ninja_llm、pagination 等
├── admin/          # system_config、court、cause_of_action、llm_provider、llm_record、
│                   #   document_parse_provider、redis_queue + forms/mixins
├── config/         # manager、providers/(env,yaml)、schema/(_registry_*/django/features/performance/services)、
│                   #   validators、business_config + business_rules.yaml + config.yaml、listeners、notifications
├── constants.py + data/(seed_causes_of_action.json、seed_courts.json)
├── dependencies/   # 20 个 build_* 工厂模块
├── dto/            # 跨模块 DTO（auth/cases/chat/client/contracts/.../request_context）
├── exceptions/     # base、common、chat、external、handlers、error_catalog、error_codes 等
├── filesystem/     # browse_policy、filesystem_service、folder_binding_base/crud、folder_node_path、
│                   #   inode_resolver、path_validator、storage、upload_paths
├── http/           # httpx_clients（连接池）、range、streaming
├── infrastructure/ # asgi_lifespan、cache、health、logging、monitoring、request_context、
│                   #   resource_monitor、service_locator(+base)、subprocess_runner、throttling
├── interfaces/     # Protocol + DTO + ServiceLocator 统一出口
├── llm/            # backends、circuit_breaker、client、config、fallback_policy、key_pool、
│                   #   model_list_service、prompts、router、service、streaming、structured_output、
│                   #   tracking、warmup
├── management/commands/  # analyze_performance、check_db_performance、encrypt_system_config_secrets、
│                   #   export_seed_data、init_system_config、load_seed_data、scan_orphan_files、
│                   #   scan_migration_anomalies
├── middleware/     # request_id、security、token_rate_limit
├── model_fields/encrypted.py
├── models/         # CauseOfAction、ConversationHistory、Court、DocumentParseProvider、LLMProvider、
│                   #   LLMCallRecord、PromptTemplate、SystemConfig、ToolFavorite + enums/querysets
├── protocols/ + repositories/ + security/ + service_locator_mixins/
├── services/       # browser/、court_tokens/、llm_provider/llm_stream、search、dashboard、
│                   #   cause_court、conversation、court_api_client、email、document_parse_provider、
│                   #   pdf_merge/pdf_utils/libreoffice、filename_template、material_classification、
│                   #   bound_folder_scan、prompt_template、seed_data、storage、cache、mac_clipboard、
│                   #   django_q_tasks、system_update、wiring 等
├── tasking/ + telemetry/ + utils/
```

## 数据模型

`CauseOfAction`、`ConversationHistory`、`Court`、`DocumentParseProvider`、`LLMProvider`、`LLMCallRecord`、`PromptTemplate`、`SystemConfig`、`ToolFavorite`。

## API 端点

| 前缀 | 说明 |
|------|------|
| `/api/v1/config/system-configs` | 分组列表 / 批量更新 / 创建 / 单键 PATCH/DELETE（仅管理员；敏感值 Fernet 加密存储、缓存只存密文，v27.2.7） |
| `/api/v1/llm` | chat / stream / history / templates sync / models / test-connection |
| `/api/v1/task-queue` | queued / completed / failed / scheduled / 删除 / 重提交（仅管理员，v27.2.7） |
| `/api/v1/search`、`/api/v1/dashboard/stats` | 全局搜索 / 仪表盘 |
| `/api/v1/health`（+ live/ready/detail）、`/api/v1/resource/*` | 健康检查 / 资源与 Prometheus 指标 |

## 快速上手（常用入口）

```python
# 配置
from apps.core.config import get_config_manager, get_config_value

# 异常
from apps.core.exceptions import ValidationException, PermissionDenied, NotFoundError, ConflictError

# 验证器（Utils 类方法）
from apps.core.utils.validators import Validators
Validators.validate_phone("138****8000")   # 抛 ValidationException（示例为占位号）

# 服务定位器
from apps.core.interfaces import ServiceLocator
llm = ServiceLocator.get_llm_service()

# 性能监控装饰器
from apps.core.infrastructure.monitoring import PerformanceMonitor

# 浏览器
from apps.core.services.browser import create_browser
with create_browser() as (page, context):
    page.goto("https://example.com")
```

## 依赖关系

被约 35 个 app 依赖（基础设施层）；经 ServiceLocator mixins 懒加载反向触达 documents / contract_review / workbench 等业务服务。

## 测试

```bash
cd backend
env -u PYTHONHOME -u PYTHONPATH DB_NAME=test_fachuan_dev \
  .venv/bin/pytest tests/ci/unit/core/ -q --reuse-db --timeout=900
```
