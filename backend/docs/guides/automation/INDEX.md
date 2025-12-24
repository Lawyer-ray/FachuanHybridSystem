# 📚 自动化工具 - 文档索引

## 📖 文档列表

### 1. [README.md](README.md) - 模块概述
- 功能概述
- 架构设计
- 核心服务
- 开发指南
- 快速开始

**适合**: 新手入门、了解整体架构

---

### 2. [QUICKSTART.md](QUICKSTART.md) - 快速启动指南
- 5 分钟快速上手
- 依赖安装
- 启动服务
- 测试链接
- 常见问题

**适合**: 快速测试、验证功能

---

### 3. [COURT_DOCUMENT_GUIDE.md](COURT_DOCUMENT_GUIDE.md) - 法院文书下载指南
- 支持的链接类型
- 使用方法（3 种）
- 下载结果格式
- 文件存储路径
- 错误处理
- 与其他模块集成

**适合**: 使用文书下载功能

---

### 4. [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - 实现总结
- 已完成的工作
- 核心功能
- 文件清单
- 返回结果格式
- 下一步工作

**适合**: 了解实现细节、开发进度

---

### 5. [REVIEW.md](REVIEW.md) - 代码审查报告
- 架构设计评分
- 代码质量分析
- 优秀设计点
- 需要注意的问题
- 配置清单

**适合**: 代码审查、质量评估

---

## 🎯 按场景查找文档

### 我想快速测试文书下载
👉 [QUICKSTART.md](QUICKSTART.md)

### 我想了解如何使用文书下载
👉 [COURT_DOCUMENT_GUIDE.md](COURT_DOCUMENT_GUIDE.md)

### 我想开发新的爬虫
👉 [README.md#开发新爬虫](README.md)

### 我想了解整体架构
👉 [README.md](README.md) + [REVIEW.md](REVIEW.md)

### 我遇到了问题
👉 [COURT_DOCUMENT_GUIDE.md#错误处理](COURT_DOCUMENT_GUIDE.md) + [QUICKSTART.md#常见问题](QUICKSTART.md)

---

## 📂 文档结构

```
automation/
├── README.md                       # 简洁入口（指向 docs/）
│
└── docs/                           # 📚 所有文档都在这里
    ├── INDEX.md                        # 📍 你在这里
    ├── README.md                       # 模块概述（完整）
    ├── QUICKSTART.md                   # 快速启动（5分钟）
    ├── COURT_DOCUMENT_GUIDE.md         # 文书下载指南（详细）
    ├── IMPLEMENTATION_SUMMARY.md       # 实现总结（技术）
    ├── REVIEW.md                       # 代码审查（质量）
    ├── STRUCTURE.md                    # 目录结构说明
    └── CHANGELOG.md                    # 变更日志
```

---

## 🔄 文档更新日志

### 2024-11-27
- ✅ 创建文档索引
- ✅ 整理文档结构
- ✅ 完成法院文书下载文档

---

## 💡 文档编写规范

1. **使用 Emoji** - 提高可读性
2. **代码示例** - 提供可运行的代码
3. **截图说明** - 关键步骤配图
4. **常见问题** - 预判用户疑问
5. **更新日志** - 记录变更历史
