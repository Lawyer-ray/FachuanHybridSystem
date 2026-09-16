# 法穿 AI Copilot —— 新一代前端

律师的作业台。材料预处理 + 办案 的 all-in-one 前台，替代旧的 `frontend_2026`。

- **品牌名**：法穿 AI Copilot
- **定位**：单人律师的作业台。不做权限体系、多角色、协作与审批流，评价标准只有一条——顺不顺手。
- **切入点**：材料预处理（这堆材料是什么？要拆成几份？）→ 办案（这个案子到哪一步了？）
- **后端**：Django + Ninja，同仓库 `backend/`，共用同一套 `/api/v1`。

## 技术栈

| 类别 | 选型 |
|---|---|
| 框架 | React 19 + TypeScript ~6.0（strict） |
| 构建 | Vite 8（`@vitejs/plugin-react-swc`） |
| 路由 | react-router v7 |
| 服务端状态 | @tanstack/react-query v5 |
| 客户端状态 | Zustand v5 |
| UI 基础 | @radix-ui（shadcn 风格，`components/ui/`）+ lucide-react |
| 样式 | Tailwind CSS v4（`index.css` 主题变量 + 语义色，暗色 `.dark`） |
| HTTP | ky（经 `src/lib/api.ts` 封装） |
| 配件 | clsx / tailwind-merge / class-variance-authority |
| 通知 | sonner |
| 日期 | date-fns |
| PDF | pdfjs-dist |
| 测试 | vitest v4 |

## 快速开始

```bash
# 依赖
pnpm install

# 开发服务器（默认 http://localhost:5090，/api 代理到 http://127.0.0.1:8002）
pnpm dev

# 生产构建（含 tsc -b 类型检查）
pnpm build

# ESLint
pnpm lint

# Vitest 单测
pnpm test
```

> 端口约定：dev 端口 `5090`。如需变更，务必同步 `backend/.env` 的 `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS`，否则浏览器跨域拦截会导致登录失败。

## 目录结构（feature-first）

核心目录组织遵循「feature-first」。增长靠**新增 feature 目录**，不靠改造既有目录。详见 [`CLAUDE.md`](./CLAUDE.md)（前端规范唯一权威来源）。

```
src/
├── app/                  # 应用装配：router / paths / providers
├── components/
│   ├── ui/               # shadcn 基础组件（与业务无关）
│   └── shared/           # 跨 feature 复用的业务无关组件
├── features/             # ★ 业务域（核心组织单元）
│   ├── auth/             # 登录
│   ├── material-prep/    # 材料预处理（复杂 feature 的标准样板）
│   └── .../
├── hooks/                # 跨 feature 通用 hooks
├── lib/                  # 纯工具（api 客户端工厂、utils、date…）
├── types/                # 全局类型
├── config/               # 运行时配置
└── index.css             # 主题 + 语义色令牌 + 全局基类
```

每个 feature 同构（`types/constants/api/schemas/store/domain/hooks/components/index` ），复杂子域向下开一级（如 `materials-prep/components/reader/`）。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8002/api/v1` | API 基址 |
| `VITE_BACKEND_URL` | `http://localhost:8002` | 后端地址（登录跳转等） |

运行时也支持 `localStorage` 的 `api_base_url` / `backend_url` 覆盖（优先于环境变量）。

## 开发约定（摘要）

- **文件规模红线**：≤200 行理想；>350 软红线触发拆分；>450 硬红线禁止。拆分先判单一职责，手法依次为抽子组件 → 抽 Hook → 抽纯函数模块 → 子域下行。
- **归属**：新业务归入已有 feature 或新建 feature，禁止平铺进 `pages/`；禁止 feature 间互相 import。
- **提权审慎**：shared / hooks / lib 只在 ≥2 个 feature 都使用时才上提。
- 完整约束见 [`CLAUDE.md`](./CLAUDE.md)。

## CI

`.github/workflows/frontend-ci.yml`：PR / push（main/master/dev）且 `frontend/` 有变更时触发，执行 TypeScript 类型检查、ESLint、Vite build。