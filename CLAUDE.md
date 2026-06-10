# 法穿AI Copilot

## 项目概述

法律事务管理系统，帮助律师管理案件、文书、客户、财务等。开源项目，管理员需自行配置 SMTP、短信等外部服务。

## 项目结构

```
FachuanHybridSystem/
├── CLAUDE.md           # 本文件：项目概览 + 跨端规则
├── backend/            # Django 后端（详见 backend/CLAUDE.md）
│   ├── apiSystem/      # Django 项目配置
│   ├── apps/           # 业务模块
│   └── tests/          # 测试
├── frontend/           # React 前端（详见 frontend/CLAUDE.md）
│   └── src/
│       ├── components/ # 通用 UI 组件
│       ├── features/   # 业务模块（按功能划分）
│       ├── layouts/    # 布局组件
│       ├── lib/        # 工具库
│       ├── routes/     # 路由配置
│       └── stores/     # 状态管理
├── java-services/      # Java 微服务（详见 CLAUDE.md in java-services/）
│   ├── pom.xml         # Maven 父 POM
│   ├── shared/         # 共享代码（common-models, poi-utils）
│   ├── poi-service/    # POI 文档生成服务
│   └── tests/          # Python 集成测试
├── docs/               # 文档
└── changelog/          # 版本日志
```

## 关键架构约定

### 文件名模板可配置化

新增/修改文件名生成逻辑时，**必须使用 `FilenameTemplateService`**（`apps.core.services.filename_template_service`），禁止在业务代码中硬编码文件名格式。

### 路径处理规范（跨平台兼容）

**禁止模式**：
```python
# ❌ str() 在 Windows 上返回反斜杠
relative_path = str(file_path.relative_to(media_root))
```

**正确模式**：
```python
# ✅ 始终使用 as_posix() 返回正斜杠
relative_path = file_path.relative_to(media_root).as_posix()
```

## 红线规则（全端通用）

- 对接外部 API 时，必须先拿到确切的 curl 命令或请求/响应数据再写代码
- 不要在 commit message 中添加 Co-Authored-By trailer
- 代码改动完成后必须立即 commit，不要等用户提醒
- `git push` 必须等用户明确确认后才能执行
- 所有改动必须在非 main 分支上进行
- CHANGELOG 和 package.json 版本号：仅在用户明确要求时才更新
- CHANGELOG 格式：在 `changelog/` 目录下新建独立文件 `v{版本号}.md`，不要直接编辑 `CHANGELOG.md`

### 标准 PR 流程

1. **隐私检查**：扫描 diff 中的 PII
2. **确认全部已 commit**：`git status` 无未提交改动
3. **本地 CI 全绿**：`make ci`
4. **推送到远端**：等用户确认后执行 `git push`
5. **等待用户确认提 PR**
6. **创建 PR**：`gh pr create`，PR 描述包含 Summary + Test plan
7. **监控 GitHub CI**：`gh pr checks <PR#> --watch`
8. **合并 PR**：`gh pr merge <PR#> --merge`
9. **切回 main 同步**

## 分支策略：main + community

| 分支 | 定位 | 说明 |
|:---|:---|:---|
| `main` | 作者维护原始逻辑 | 只包含作者审核过的代码 |
| `community` | 社区版 | 接受所有外部 PR，作者不定期 cherry-pick 到 main |

### 规则

1. **外部贡献者**：PR 必须提交到 `community` 分支
2. **作者开发**：在 main 上开功能分支，走标准 PR 流程
3. **main → community 同步**：cherry-pick，**禁止 `git merge main`**
4. **community → main 挑选**：从 community 中挑选有价值的 commit，cherry-pick 到 main 的功能分支
5. **禁止反向合并**：`git merge community` 到 main 是严格禁止的

## 后端地址

- 后台管理：`http://127.0.0.1:8002/admin`
- API 文档：`http://127.0.0.1:8002/api/v1/docs`
- 前端开发：`http://localhost:5173`

## Java 微服务

Java 微服务位于 `java-services/`，采用 Maven 多模块结构。技术栈和开发规范详见 `java-services/CLAUDE.md`。

**添加新 Java 服务**：
1. 在 `java-services/` 下新建子目录
2. 创建 `pom.xml` 继承父 POM
3. 在父 POM 的 `<modules>` 中添加新模块
4. 共享代码放 `java-services/shared/`
