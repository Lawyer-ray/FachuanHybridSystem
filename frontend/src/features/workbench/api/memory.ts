/**
 * 项目 AI 笔记的只读列表（项目页「AI 上下文」面板的数据源）。
 *
 * 端点 `GET /api/v1/agent/memory?contract_id=<合同id>`（`backend/apps/agent/api/memory_api.py`
 * 的 `list_memories`）：`contract_id` 过滤后只剩挂在本项目上的笔记；写入侧在 AI
 * 助手那边（回答下方的书签 → `POST /agent/memory/notes`，锚点由服务端按会话反查）。
 *
 * **为什么不复用 copilot 的 `AgentMemoryItem`**：那个类型是「助手记忆」管理面
 * （个人/团队/律所三级、可增删确认），本项目页只读展示，只要内容/来源/锚点。
 * 跨 feature 引 copilot 的内部 api 模块也被 eslint 的 no-restricted-imports 拦着
 * （见 frontend/CLAUDE.md「归属与提权硬规则」），故本域自持一份展示子集。
 */

import { createApiClient } from '@/lib/api'

/** `GET /agent/memory` 的一行（后端 `MemoryOut` 的展示子集，snake_case 与响应同形） */
export interface ProjectNote {
  id: string
  content: string
  /** 非空 = 已有人确认过，是项目事实；空串 = 未经确认的同事判断 */
  confirmed_at: string
  /** 确认人姓名；未确认时为空串，后端不保证一定有名字 */
  confirmed_by: string
  /** 非空 = 挂在本案上；null = 挂在项目（合同）上 */
  case_id: number | null
  created_at: string
  /** 已被后来的条目推翻：注入不会用它，面板要标出来，否则会并排显示两条矛盾结论 */
  is_superseded: boolean
}

/** agent 前缀只有本文件用，不放进 `api/client.ts`（那里是跨资源共用的实例） */
const agentApi = createApiClient({ prefix: '/api/v1/agent' })

/** 本项目下的 AI 笔记（默认 50 条，够铺满抽屉且不让打开动作拖出长请求） */
export function listProjectNotes(contractId: number, limit = 50): Promise<ProjectNote[]> {
  return agentApi.get('memory', { searchParams: { contract_id: contractId, limit } }).json<ProjectNote[]>()
}
