# 运维 Runbook（Backend）

## 启动前检查
- Python 版本：3.12
- Django：6.0.x
- 生产必须配置：`DJANGO_SECRET_KEY`、`CREDENTIAL_ENCRYPTION_KEY`（Fernet）
- 生产必须配置：`CORS_ALLOWED_ORIGINS`、`CSRF_TRUSTED_ORIGINS`
- 多进程/多副本：必须配置 `DJANGO_CACHE_REDIS_URL` 与 `DJANGO_CHANNEL_REDIS_URL`

## 环境变量清单（核心）
- `DJANGO_DEBUG`：`0/1`，生产应为 `0`
- `DJANGO_ALLOWED_HOSTS`：逗号分隔
- `DJANGO_SECRET_KEY`：生产强制为高强度值
- `CREDENTIAL_ENCRYPTION_KEY`：Fernet key（生产强制）
- `SCRAPER_ENCRYPTION_KEY`：可选；不设置则回退到 `CREDENTIAL_ENCRYPTION_KEY`
- `CORS_ALLOWED_ORIGINS`、`CSRF_TRUSTED_ORIGINS`：生产强制白名单
- `DJANGO_CACHE_REDIS_URL`：Redis cache
- `DJANGO_CHANNEL_REDIS_URL`：Channels Redis channel layer
- `SENTRY_DSN`、`SENTRY_TRACES_SAMPLE_RATE`：可选

## 数据库策略
### SQLite（默认）
- 适合单机/轻量场景
- 配置：`DATABASE_PATH=/data/db.sqlite3`

### Postgres（推荐生产路径）
- 配置：`DB_ENGINE=postgres`，并设置 `DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT`
- 容器示例：`deploy/docker/docker-compose.yml` + `deploy/docker/docker-compose.postgres.yml`

## 数据库迁移与回滚（Schema/Data）
本节描述 Django 数据库迁移（`migrations/`）的上线与回滚策略；不包含“配置迁移/回滚系统”（两者概念不同）。

### 上线前检查
- 确认本次变更涉及的迁移文件已生成且可重复执行（无依赖外部环境的副作用）
- 评估是否存在破坏性变更：删除列/表、重命名、类型收窄、唯一约束新增、默认值回填等
- 对大表操作优先采用“分阶段迁移”：
  - 先加新字段/索引（可为空、写双份）
  - 回填数据（后台任务/脚本，分批）
  - 切读写到新字段
  - 最后移除旧字段/约束
- 明确回滚边界：仅 schema 回退还是需要 data 回退（多数 data 变更不可逆）

### 上线步骤（建议）
- 发布前先做数据库备份（见下节）
- 先在预发布环境执行 `python backend/apiSystem/manage.py migrate --plan` 核对迁移顺序与依赖
- 再执行 `python backend/apiSystem/manage.py migrate`，观察迁移耗时与锁等待
- 如迁移耗时/锁风险较高，优先选择低峰窗口或采用分阶段迁移方案

### 回滚策略
- 优先“应用回滚”兜底：如果迁移是向前兼容的（新增字段/索引），通常仅回滚应用即可恢复服务
- Schema 回滚（谨慎）：`python backend/apiSystem/manage.py migrate <app_label> <migration_name>`
  - 仅在确认该回滚不会丢数据或不会破坏线上读写路径时执行
- Data 回滚：
  - 若数据变更不可逆（覆盖写/删除），只能依赖备份恢复或离线修复脚本
  - 强烈建议对“数据破坏性迁移”做上线演练与恢复预案

### 备份与恢复演练
- SQLite：
  - 备份：对数据库文件做一致性拷贝（服务停写或使用文件系统快照）
  - 恢复：替换数据库文件并重启服务
- Postgres：
  - 备份：使用 `pg_dump`（逻辑备份）或存储快照（云厂商能力）
  - 恢复：使用 `pg_restore`（逻辑恢复）或回滚快照
- 演练要求：
  - 至少每季度做一次“备份可恢复”演练（包含校验：关键表行数/业务抽样读写）
  - 记录恢复耗时与依赖项（密钥、连接串、权限、版本）

## 任务队列（Django-Q）
- 运行 `qcluster` 前确认：数据库可用、Redis（如启用）可用
- 生产建议配置：`DJANGO_Q_WORKERS`、`DJANGO_Q_TIMEOUT`、`DJANGO_Q_RETRY`

## 健康检查与探针
- `/api/v1/health/live`：存活探针
- `/api/v1/health/ready`：就绪探针
- `/api/v1/health`：整体健康状态
- `/api/v1/health/detail`：仅管理员可访问

## 日志与排障
- 默认输出结构化字段：`request_id/trace_id/span_id`
- 排障优先顺序：
  - 先按 `request_id` 串联 nginx/ingress 与应用日志
  - 再按 `trace_id` 关联异步任务与外部调用（如启用）

## Metrics 与容量
- `/api/v1/resource/metrics`：JSON 指标快照（管理员）
- `/api/v1/resource/metrics/prometheus`：Prometheus 文本（管理员）
- 建议告警：
  - 5xx 占比升高、p95/p99 延迟升高
  - 外呼 httpx 5xx/timeout 增加
  - Redis 不可用（多进程场景会导致限流不一致）

## 密钥轮换
- `DJANGO_SECRET_KEY`：滚动发布窗口内完成；确保新旧实例一致
- `CREDENTIAL_ENCRYPTION_KEY`：轮换前先评估历史密文兼容策略；建议引入双写/多 key 解密窗口后再切换
