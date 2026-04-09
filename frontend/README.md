# 法穿 AI 前端

## 项目版本

- **当前版本**：`0.0.1`
- **状态说明**：当前前端处于独立迭代阶段，**暂未与 backend 完全对齐**（接口、字段与部分业务流程仍在持续联调中）。

## 项目简介

`frontend/` 是法穿 AI 的 Web 前端工程，基于 React + TypeScript + Vite 构建，承担公开页面、认证页面与后台管理页面的交互实现。

## 技术栈

- **框架**：React 19、TypeScript、Vite
- **路由**：React Router v7（含懒加载）
- **状态与请求**：Zustand、TanStack Query、Ky
- **UI 体系**：Tailwind CSS 4、Radix UI、Lucide Icons、Sonner
- **表单与校验**：React Hook Form、Zod

## 当前已实现功能

### 1) 公开页面

- 首页（`/`）
- 定价页（`/pricing`）
- 教程页（`/tutorial`）

### 2) 认证与会话

- 登录（`/login`）
- 注册（`/register`）
- 基于 JWT 的 token 存储、刷新与 401 自动重试
- 基础路由守卫（访客页守卫、后台鉴权守卫）

### 3) 后台管理主干

- 仪表盘（`/admin/dashboard`）
- 收件箱（列表/详情）
- 当事人管理（列表、新建、详情、编辑）
- 案件管理（列表、新建、详情、编辑）
- 合同管理（列表、新建、详情、编辑）
- 提醒管理（列表入口）

### 4) 组织管理

- 组织管理主页面
- 律所管理（列表/新建/详情/编辑）
- 律师管理（列表/新建/详情/编辑）
- 团队与账号凭证 Tab 入口

### 5) 自动化工具

- 自动化工具首页
- 财产保全询价（列表/详情）
- 文书智能识别（列表/详情）

## 当前未完全对齐项（阶段性说明）

- **接口契约仍在联调**：部分页面字段与后端返回结构可能发生变动。
- **部分模块仍是占位入口**：如 `documents`、`settings`、`portal` 等目录当前以路由或结构占位为主。
- **少量前端 TODO 待处理**：例如个别子能力依赖后端补充独立 CRUD 接口后再接入。

## 本地开发

```bash
pnpm install
pnpm dev
```

常用命令：

```bash
pnpm build
pnpm lint
pnpm preview
```

## 推送建议

提交前请确保以下目录不入库：

- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/.env*`

以上目录已在忽略规则中配置。