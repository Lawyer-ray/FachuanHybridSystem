# src/types

全局类型目录（feature 内类型仍就近放各自 `types.ts`，不沉到这里）。

- `api-schema.d.ts` —— 后端 OpenAPI 生成物（openapi-typescript 自动生成，勿手改）
- `api-schema.demo.ts` —— 生成物的示范消费 + 编译期冒烟（tsc 守卫 schema 漂移）

## api-schema.d.ts 再生成流程

后端路由 / 返回结构变更后，按顺序执行（两份生成物均入库，随代码一起提交）：

```bash
# 1. 导出后端 OpenAPI JSON（管理命令，默认写 backend/openapi.json）
cd backend && .venv/bin/python apiSystem/manage.py export_openapi_schema

# 2. 生成前端类型（package.json script：openapi-typescript ../backend/openapi.json）
cd frontend && pnpm gen:api
```

## 渐进迁移路径

现有 feature 手写的接口类型（`features/*/api.ts`、`features/*/types.ts`）不强制替换。
下次实质改动某个手写类型时，优先改为从生成物取形状，消除「手抄漂移」：

```ts
import type { components, operations } from '@/types/api-schema'

type Row = components['schemas']['CaseSearchResultSchema'] // 按 schema 名取
type Resp =
  operations['<operationId>']['responses'][200]['content']['application/json'] // 按端点取
```

operationId 可在 `api-schema.d.ts` 的 `operations` 段或 `backend/openapi.json` 中检索
（形状为 `模块路径_函数名`，如 `apps_document_recognition_api_document_recognition_api_search_cases_for_binding`）。
完整示例见 `api-schema.demo.ts`。
