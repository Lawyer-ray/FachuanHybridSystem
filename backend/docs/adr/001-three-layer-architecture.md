# ADR-001: 采用三层架构

## 状态

已接受 (2024-01-15)

## 背景

在项目初期，代码结构混乱，存在以下问题：

1. **职责不清**：API 层包含业务逻辑，Service 层包含 HTTP 处理
2. **难以测试**：业务逻辑与 HTTP 请求耦合，无法独立测试
3. **难以维护**：修改业务逻辑需要同时修改多个层次
4. **代码重复**：相同的业务逻辑在多处重复实现

这些问题导致：
- 开发效率低下
- Bug 频发
- 新功能开发困难
- 代码质量下降

## 决策

我们决定采用**三层架构**（Three-Layer Architecture），明确划分职责：

```
API Layer (API 层)
    ↓
Service Layer (服务层)
    ↓
Model Layer (模型层)
```

### API 层职责

**只能做**：
- 接收 HTTP 请求，验证参数（通过 Schema）
- 调用 Service 层方法
- 将 Service 返回值转换为 HTTP 响应
- 捕获异常并转换为 HTTP 错误响应

**不能做**：
- 包含任何业务判断逻辑
- 直接访问数据库
- 执行权限检查
- 处理事务

### Service 层职责

**只能做**：
- 封装所有业务逻辑和业务规则
- 管理数据库事务
- 执行权限检查
- 协调多个 Model 的操作
- 通过 Protocol 接口调用其他模块
- 抛出自定义业务异常

**不能做**：
- 访问 HTTP request 对象
- 返回 HTTP 响应对象
- 包含 HTTP 状态码逻辑

### Model 层职责

**只能做**：
- 定义数据库表结构
- 简单的数据验证
- 简单的属性方法
- 数据库级别的约束

**不能做**：
- 复杂的业务逻辑
- 跨表的复杂查询
- 调用其他模块的 Model

## 后果

### 正面影响

1. **职责清晰**：每一层都有明确的职责，易于理解和维护
2. **可测试性提升**：Service 层可以独立测试，不依赖 HTTP 请求
3. **代码复用**：Service 层的业务逻辑可以在多个 API 端点复用
4. **易于重构**：修改某一层不影响其他层
5. **团队协作**：不同开发者可以并行开发不同层次
6. **降低耦合**：层与层之间通过接口通信，降低耦合度

### 负面影响

1. **代码量增加**：需要编写更多的样板代码（Service 类、接口等）
2. **学习曲线**：新开发者需要理解架构原则
3. **初期开发速度**：遵循架构规范会降低初期开发速度

### 风险

1. **架构违反**：开发者可能不遵循架构原则，导致代码腐化
   - **缓解措施**：编写详细的开发规范文档，进行代码审查
2. **过度设计**：简单功能也使用复杂的架构
   - **缓解措施**：根据功能复杂度灵活应用，简单功能可以简化

## 替代方案

### 方案 1: MVC 架构

传统的 MVC（Model-View-Controller）架构。

**优点**：
- Django 原生支持
- 开发者熟悉
- 简单直接

**缺点**：
- Controller 容易变得臃肿
- 业务逻辑容易泄漏到 View 或 Model
- 难以测试复杂业务逻辑

### 方案 2: 领域驱动设计（DDD）

采用完整的 DDD 架构，包括聚合根、值对象、领域服务等。

**优点**：
- 更好地表达业务领域
- 适合复杂业务场景
- 高度解耦

**缺点**：
- 学习曲线陡峭
- 实施成本高
- 对于中小型项目过于复杂

### 方案 3: 微服务架构

将系统拆分为多个独立的微服务。

**优点**：
- 独立部署
- 技术栈灵活
- 易于扩展

**缺点**：
- 运维复杂度高
- 分布式事务困难
- 对于单体应用过于复杂

## 实施

### 阶段 1: 基础设施（已完成）

1. 创建 `apps/core/exceptions.py` - 统一异常体系
2. 创建 `apps/core/interfaces.py` - Protocol 接口定义
3. 更新 `.kiro/steering/django-python-expert.md` - 开发规范

### 阶段 2: 模块重构（已完成）

1. 重构 `automation` 模块
2. 重构 `cases` 模块
3. 重构 `contracts` 模块
4. 重构 `client` 模块
5. 重构 `organization` 模块

### 阶段 3: 测试和文档（已完成）

1. 编写单元测试
2. 编写集成测试
3. 编写 Property-Based Testing
4. 更新 API 文档
5. 创建架构决策记录

### 阶段 4: 持续改进（进行中）

1. 代码审查
2. 性能监控
3. 架构健康度检查
4. 团队培训

## 参考资料

- [Clean Architecture by Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [Django Best Practices](https://django-best-practices.readthedocs.io/)
- 项目规范文档：`.kiro/steering/django-python-expert.md`
- 设计文档：`.kiro/specs/backend-architecture-refactoring/design.md`

## 更新历史

- 2024-01-15: 初始版本，决策已接受
- 2024-01-20: 完成所有模块重构
- 2024-01-25: 添加测试和文档
