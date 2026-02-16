# 架构训练

本文档用于帮助新同学快速理解本项目的后端架构、模块边界与常见约束。

## 1. 目录与分层

- `apiSystem/`：Django 工程入口（settings/urls/asgi/wsgi）
- `apps/`：按业务域拆分的 Django apps（cases/contracts/client/documents/...）
- `tests/`：集中化测试（unit / integration / property / structure）

## 2. API 入口与异常处理

- API 框架：django-ninja，路由统一注册在工程入口侧
- 异常处理：统一异常处理器，保证响应结构一致（success/code/message/errors）
- Health endpoints：提供 live/ready/detail 等健康检查端点（便于部署与运维）

## 3. 跨模块协作：Protocol + Adapter + ServiceLocator

本项目推荐用“能力契约”来跨域协作：

- **Protocol**：定义跨模块可调用能力的最小接口（typing.Protocol）
- **Adapter**：在目标模块内实现 Protocol，封装 ORM/外部集成细节
- **ServiceLocator**：在 wiring/api 工厂处组装依赖，避免 service 之间硬编码耦合

收益：

- 防止 services 层跨模块直接 import models
- 降低循环依赖概率
- 让测试可替换依赖（更容易写 unit test）

## 4. 结构测试（Architecture Guardrails）

`backend/tests/structure/` 是架构稳定性的关键护栏，常见约束包括：

- 禁止某些目录出现越界导入
- 限制 service/adapters 直接写 ORM 的方式
- 对安全/限流/健康检查等关键能力的“不得回退”约束

实践建议：

- 新增跨模块能力优先补结构测试，再补单测
- 结构测试失败优先修边界，而不是在测试里加豁免

## 5. 常见反模式

- 在 `apps/*/services/**` 中跨模块直接 import models
- Adapter 里写成第二套业务 service（职责漂移）
- try/except 吞异常（排障成本指数级上升）
- 为了“复用”把大量业务塞进 `utils.py`（最后变成隐式 service）
