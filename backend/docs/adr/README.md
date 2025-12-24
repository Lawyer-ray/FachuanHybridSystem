# 架构决策记录（Architecture Decision Records）

## 什么是 ADR？

架构决策记录（ADR）是记录项目中重要架构决策的文档。每个 ADR 描述一个具体的架构决策，包括：

- **背景**：为什么需要做这个决策
- **决策**：我们决定做什么
- **后果**：这个决策带来的影响（正面和负面）
- **状态**：已接受、已弃用、已替代等

## ADR 列表

| 编号 | 标题 | 状态 | 日期 |
|------|------|------|------|
| [001](001-three-layer-architecture.md) | 采用三层架构 | 已接受 | 2024-01-15 |
| [002](002-dependency-injection.md) | 使用依赖注入 | 已接受 | 2024-01-15 |
| [003](003-protocol-interface.md) | Protocol 接口解耦 | 已接受 | 2024-01-15 |
| [004](004-exception-handling.md) | 统一异常处理 | 已接受 | 2024-01-15 |
| [005](005-query-optimization.md) | 数据库查询优化策略 | 已接受 | 2024-01-16 |
| [006](006-testing-strategy.md) | 测试策略 | 已接受 | 2024-01-16 |

## 如何使用 ADR

### 创建新的 ADR

1. 复制 `template.md` 文件
2. 重命名为 `XXX-title.md`（XXX 是下一个编号）
3. 填写内容
4. 更新本 README 的列表

### ADR 模板

参见 [template.md](template.md)

## 参考资料

- [ADR GitHub Organization](https://adr.github.io/)
- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
