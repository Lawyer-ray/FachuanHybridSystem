# 项目文档索引

本目录包含法传混合系统后端的所有项目文档，按类型组织以便快速查找和维护。

## 📁 目录结构

```
docs/
├── README.md                # 本文件 - 文档索引
├── adr/                     # Architecture Decision Records
│   ├── 001-three-layer-architecture.md
│   ├── 002-dependency-injection.md
│   ├── 003-protocol-interface.md
│   ├── 004-exception-handling.md
│   ├── 005-query-optimization.md
│   ├── 006-testing-strategy.md
│   └── template.md
├── api/                     # API 文档
│   ├── API.md              # API 端点规范
│   ├── AUTO_TOKEN_ACQUISITION_API.md  # 自动Token获取 API 文档 ⭐
│   ├── COURT_DOCUMENT_API.md  # 法院文书下载 API 文档 ⭐
│   └── CAPTCHA_API_ROUTING.md  # 验证码 API 路由
├── architecture/            # 架构文档
│   ├── ARCHITECTURE_TRAINING.md
│   ├── REFACTORING_BEST_PRACTICES.md
│   ├── SUPERVISING_AUTHORITY_FEATURE.md
│   └── insurance/          # 保险服务架构
│       └── RETRY_MECHANISM.md
├── archive/                 # 归档文档
│   ├── admin-test-reports/ # Admin 测试报告归档
│   ├── insurance-dev-notes/ # 保险服务开发笔记归档
│   ├── CLEANUP_REPORT.md   # 项目清理报告
│   └── PERFORMANCE_TEST_RESULTS.md
├── examples/                # 示例代码 ⭐
│   ├── README.md           # 示例代码索引
│   └── AUTO_TOKEN_ACQUISITION_EXAMPLES.md  # 自动Token获取示例
├── guides/                  # 开发指南
│   ├── AUTO_TOKEN_ACQUISITION_INTEGRATION_GUIDE.md  # 自动Token获取集成指南 ⭐
│   ├── CODE_REVIEW_CHECKLIST.md
│   ├── CODE_REVIEW_PROCESS.md
│   ├── COURT_DOCUMENT_DOWNLOAD_GUIDE.md  # 法院文书下载指南 ⭐
│   ├── COURT_DOCUMENT_QUICK_REFERENCE.md  # 法院文书下载快速参考 ⭐
│   ├── FILE_ORGANIZATION.md
│   ├── MIGRATION_GUIDE.md
│   ├── QUICK_START.md
│   └── TEAM_KNOWLEDGE_SHARING.md
├── operations/              # 运维文档
│   ├── CONFIG_UPDATE_SUMMARY.md
│   ├── COURT_DOCUMENT_CONFIG.md  # 法院文书下载配置 ⭐
│   ├── DATA_RECOVERY_GUIDE.md
│   ├── MIGRATION_VERIFICATION_REPORT.md
│   ├── PERFORMANCE_MONITORING_IMPLEMENTATION.md
│   └── PERFORMANCE_MONITORING.md
└── quality/                 # 质量文档
    └── CODE_QUALITY_REVIEW.md
```

## 📚 文档分类

### ADR - Architecture Decision Records (`adr/`)

记录重要的架构决策：

- **001-three-layer-architecture.md** - 采用三层架构
- **002-dependency-injection.md** - 使用依赖注入
- **003-protocol-interface.md** - Protocol 接口解耦
- **004-exception-handling.md** - 统一异常处理
- **005-query-optimization.md** - 查询优化策略
- **006-testing-strategy.md** - 测试策略

**适用场景**：
- 了解架构决策背景
- 新架构决策参考
- 技术方案评审

### API 文档 (`api/`)

API 相关的文档和规范：

- **API.md** - 完整的 API 端点文档
  - 认证和授权
  - 请求/响应格式
  - 错误码说明
  - 使用示例

- **AUTO_TOKEN_ACQUISITION_API.md** - 自动Token获取 API 文档 ⭐
  - 核心接口和DTO定义
  - 异常处理和错误码
  - ServiceLocator使用方式
  - 完整的使用示例和最佳实践

- **COURT_DOCUMENT_API.md** - 法院文书下载 API 文档 ⭐
  - API 端点详细说明
  - 请求/响应示例
  - Python/JavaScript/cURL 使用示例
  - 错误码说明

- **CAPTCHA_API_ROUTING.md** - 验证码 API 路由说明
  - 验证码识别接口
  - 路由配置

**适用场景**：
- 前端开发人员需要了解 API 接口
- 编写 API 集成测试
- 第三方系统对接

### 架构文档 (`architecture/`)

系统架构、设计决策和最佳实践：

- **ARCHITECTURE_TRAINING.md** - 架构培训材料
  - 5 周完整培训计划
  - 三层架构详解
  - 依赖注入和接口解耦
  - 实战演练和评估

- **REFACTORING_BEST_PRACTICES.md** - 重构最佳实践
  - 重构经验总结
  - 常见陷阱和解决方案
  - 成功案例分析
  - 重构清单

- **SUPERVISING_AUTHORITY_FEATURE.md** - 监督机关功能设计

- **insurance/** - 保险服务架构文档
  - **RETRY_MECHANISM.md** - 重试机制设计

**适用场景**：
- 新成员入职培训
- 架构决策参考
- 代码重构指导
- 技术方案评审

### 归档文档 (`archive/`)

历史文档和开发笔记归档：

- **admin-test-reports/** - Admin 测试报告归档
  - 包含历史测试报告和阶段性总结
  - 仅供历史参考

- **insurance-dev-notes/** - 保险服务开发笔记归档
  - API 修复记录
  - 错误处理增强
  - Token 和报价修复
  - 费率显示优化
  - 请求对比分析

- **CLEANUP_REPORT.md** - 项目结构清理报告
  - 清理操作记录
  - 文件移动/删除清单
  - 验证结果

- **PERFORMANCE_TEST_RESULTS.md** - 性能测试结果

**适用场景**：
- 查阅历史决策
- 了解问题解决过程
- 追溯变更历史

### 开发指南 (`guides/`)

日常开发流程和团队协作指南：

- **QUICK_START.md** - 快速开始指南
  - 环境搭建
  - 项目运行
  - 常见问题

- **AUTO_TOKEN_ACQUISITION_INTEGRATION_GUIDE.md** - 自动Token获取集成指南 ⭐
  - 完整的集成架构和步骤
  - Service适配器和增强版Service实现
  - API层集成和工厂函数模式
  - 测试策略和最佳实践
  - 性能优化和监控调试

- **COURT_DOCUMENT_DOWNLOAD_GUIDE.md** - 法院文书下载优化指南 ⭐
  - 功能概述和核心优势
  - 环境配置和使用方式
  - 工作原理和数据模型
  - 错误处理和性能优化
  - 最佳实践

- **COURT_DOCUMENT_QUICK_REFERENCE.md** - 法院文书下载快速参考 ⭐
  - 5 分钟快速开始
  - 常用命令速查
  - 配置项和数据模型速查
  - 常见问题快速解决

- **FILE_ORGANIZATION.md** - 文件组织规范
  - Django App 标准结构
  - 测试文件组织
  - 文档和脚本分类
  - 命名规范

- **MIGRATION_GUIDE.md** - 项目结构迁移指南
  - 迁移概述和主要变化
  - 文件位置变化对照
  - 导入路径更新
  - 工作流程调整
  - 迁移清单

- **CODE_REVIEW_CHECKLIST.md** - 代码审查清单
  - 架构检查
  - 代码质量检查
  - 性能检查
  - 安全检查

- **CODE_REVIEW_PROCESS.md** - 代码审查流程
  - 提交 PR 流程
  - 审查标准
  - 反馈处理

- **TEAM_KNOWLEDGE_SHARING.md** - 团队知识分享
  - 技术分享会
  - 知识库建设
  - 持续改进机制

**适用场景**：
- 新成员快速上手
- 代码审查参考
- 团队协作规范
- 知识传承

### 示例代码 (`examples/`)

各种功能的完整示例代码：

- **AUTO_TOKEN_ACQUISITION_EXAMPLES.md** - 自动Token获取功能示例 ⭐
  - 基础使用示例（简单获取、指定凭证）
  - 服务集成示例（业务服务集成、适配器模式）
  - API集成示例（Django Ninja集成）
  - 错误处理示例（完整错误处理和降级策略）
  - 性能优化示例（缓存和批量处理）
  - 监控调试示例（健康监控和诊断工具）
  - 测试示例（单元测试、集成测试、性能测试）

**适用场景**：
- 学习如何使用特定功能
- 快速上手新功能开发
- 了解最佳实践和常见模式
- 编写测试用例参考
- 性能优化和监控实现

### 运维文档 (`operations/`)

部署、监控和故障处理文档：

- **COURT_DOCUMENT_CONFIG.md** - 法院文书下载配置说明 ⭐
  - Django Settings 配置详解
  - 环境变量配置
  - 数据库和 Playwright 配置
  - 生产环境配置示例
  - 配置验证和故障排查

- **DATA_RECOVERY_GUIDE.md** - 数据恢复指南
  - 备份策略
  - 恢复流程
  - 应急预案

- **PERFORMANCE_MONITORING_IMPLEMENTATION.md** - 性能监控实施
  - 监控指标
  - 性能分析
  - 优化建议

- **PERFORMANCE_MONITORING.md** - 性能监控配置

- **CONFIG_UPDATE_SUMMARY.md** - 配置更新总结

- **MIGRATION_VERIFICATION_REPORT.md** - 迁移验证报告

**适用场景**：
- 生产环境部署
- 性能问题排查
- 数据恢复操作
- 系统监控配置

### 质量文档 (`quality/`)

代码质量标准和审查报告：

- **CODE_QUALITY_REVIEW.md** - 代码质量审查
  - 质量标准
  - 审查报告
  - 改进建议

**适用场景**：
- 代码质量评估
- 技术债务管理
- 质量改进计划

## 🔍 快速查找

### 我想了解...

#### 如何开始开发？
→ 查看 [`guides/QUICK_START.md`](guides/QUICK_START.md)

#### 如何使用自动Token获取功能？
→ 查看 [`api/AUTO_TOKEN_ACQUISITION_API.md`](api/AUTO_TOKEN_ACQUISITION_API.md) ⭐

#### 如何集成自动Token获取功能？
→ 查看 [`guides/AUTO_TOKEN_ACQUISITION_INTEGRATION_GUIDE.md`](guides/AUTO_TOKEN_ACQUISITION_INTEGRATION_GUIDE.md) ⭐

#### 自动Token获取示例代码？
→ 查看 [`examples/AUTO_TOKEN_ACQUISITION_EXAMPLES.md`](examples/AUTO_TOKEN_ACQUISITION_EXAMPLES.md) ⭐

#### 如何使用法院文书下载功能？
→ 查看 [`guides/COURT_DOCUMENT_DOWNLOAD_GUIDE.md`](guides/COURT_DOCUMENT_DOWNLOAD_GUIDE.md) ⭐

#### 项目的架构设计？
→ 查看 [`architecture/ARCHITECTURE_TRAINING.md`](architecture/ARCHITECTURE_TRAINING.md)

#### 架构决策记录？
→ 查看 [`adr/`](adr/) 目录

#### 文件应该放在哪里？
→ 查看 [`guides/FILE_ORGANIZATION.md`](guides/FILE_ORGANIZATION.md)

#### 如何适应新的项目结构？
→ 查看 [`guides/MIGRATION_GUIDE.md`](guides/MIGRATION_GUIDE.md)

#### API 接口规范？
→ 查看 [`api/API.md`](api/API.md)

#### 法院文书下载 API？
→ 查看 [`api/COURT_DOCUMENT_API.md`](api/COURT_DOCUMENT_API.md) ⭐

#### 法院文书下载配置？
→ 查看 [`operations/COURT_DOCUMENT_CONFIG.md`](operations/COURT_DOCUMENT_CONFIG.md) ⭐

#### 验证码 API 路由？
→ 查看 [`api/CAPTCHA_API_ROUTING.md`](api/CAPTCHA_API_ROUTING.md)

#### 代码审查标准？
→ 查看 [`guides/CODE_REVIEW_CHECKLIST.md`](guides/CODE_REVIEW_CHECKLIST.md)

#### 如何重构代码？
→ 查看 [`architecture/REFACTORING_BEST_PRACTICES.md`](architecture/REFACTORING_BEST_PRACTICES.md)

#### 保险服务重试机制？
→ 查看 [`architecture/insurance/RETRY_MECHANISM.md`](architecture/insurance/RETRY_MECHANISM.md)

#### 性能监控配置？
→ 查看 [`operations/PERFORMANCE_MONITORING.md`](operations/PERFORMANCE_MONITORING.md)

#### 数据恢复流程？
→ 查看 [`operations/DATA_RECOVERY_GUIDE.md`](operations/DATA_RECOVERY_GUIDE.md)

#### 项目清理报告？
→ 查看 [`archive/CLEANUP_REPORT.md`](archive/CLEANUP_REPORT.md)

#### 历史测试报告？
→ 查看 [`archive/admin-test-reports/`](archive/admin-test-reports/)

## 📝 文档维护

### 更新文档

当项目发生以下变化时，请及时更新相关文档：

- **API 变更** → 更新 `api/API.md`
- **架构调整** → 添加 ADR 到 `adr/`
- **流程优化** → 更新 `guides/` 下的相关文档
- **部署变更** → 更新 `operations/` 下的相关文档
- **历史归档** → 移动到 `archive/` 目录

### 文档规范

编写文档时请遵循以下规范：

1. **使用中文**：所有文档使用中文编写
2. **清晰的标题**：使用层级标题组织内容
3. **代码示例**：提供实际的代码示例
4. **更新日期**：在文档末尾注明最后更新日期
5. **链接引用**：使用相对路径链接其他文档

### 文档分类原则

| 文档类型 | 存放位置 |
|---------|---------|
| 架构决策 | `adr/` |
| API 规范 | `api/` |
| 系统设计 | `architecture/` |
| 开发指南 | `guides/` |
| 示例代码 | `examples/` |
| 运维文档 | `operations/` |
| 质量报告 | `quality/` |
| 历史文档 | `archive/` |

### 文档审查

文档变更需要经过审查：

- 技术文档由技术负责人审查
- 流程文档由团队讨论后确定
- 重要变更需要团队会议讨论

## 🤝 贡献指南

欢迎贡献文档！请遵循以下步骤：

1. 在相应目录下创建或修改文档
2. 更新本 README.md 的索引
3. 提交 PR 并说明变更原因
4. 等待审查和合并

## 📞 联系方式

如有文档相关问题，请联系：

- 技术文档：技术负责人
- 流程文档：项目经理
- 其他问题：团队负责人

---

**最后更新**：2025-12

**维护者**：法穿
