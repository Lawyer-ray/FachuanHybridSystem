# Code Review Process

本项目的 Code Review 目标是：在保持交付速度的前提下，持续守住“架构边界 + 安全 + 可回归”三条底线。

## 评审前（作者自检）

- 通过本地检查
  - `python apiSystem/manage.py check`
  - `pre-commit run --all-files`
  - `pytest -c pytest.ini --no-cov`（至少跑结构门禁与改动相关单测）
- 变更说明写清楚
  - What：做了什么
  - Why：为什么要做
  - How：关键实现点/兼容性影响
  - Risk：可能影响面与回滚方式
- 迁移/数据变更
  - 有 migration 时说明：是否可逆、是否影响现网数据、是否需要停机窗口

## 评审中（Reviewer 关注点）

### 1) 架构与边界

- 业务模块边界是否被破坏（尤其是 services 层跨模块直接 import models）
- 是否遵循 Protocol/Adapter/ServiceLocator 的交互方式
- 新增代码是否引入“巨石文件/巨石 service”（过长且混合多职责）
- 是否有对应的结构测试护栏，或至少不触发既有护栏（见 `backend/tests/structure/`）

### 2) 安全与隐私

- 日志是否泄露敏感信息（token、cookie、账号明文、密钥等）
- API 是否正确鉴权/鉴权失败是否可预期
- 外部输入是否校验（文件上传、路径、SQL 注入风险、模板渲染等）

### 3) 可回归与可观测性

- 关键路径是否有最小回归测试（unit 或结构测试）
- 异常是否被吞掉（尤其启动阶段/后台任务）
- 日志字段是否可追踪（request_id/trace_id、关键业务字段）

## 评审后（合并策略）

- 小步合并优先：单次 PR 聚焦一个主题
- 强制 CI 通过：workflow checks 全绿才允许合并
- 对高风险变更：合并后必须提供回归验证步骤（手动/自动均可）

## 常用检查清单

- 代码质量：`backend/docs/guides/CODE_REVIEW_CHECKLIST.md`
- 结构门禁：`backend/tests/structure/`
