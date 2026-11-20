/**
 * 项目 AI 笔记（项目页「AI 上下文」面板的数据源）。
 *
 * 端点都在 `backend/apps/agent/api/memory_api.py`：
 * `GET /api/v1/agent/memory?contract_id=<合同id>&limit=50&offset=0` 按项目读；
 * `POST /api/v1/agent/memory/{id}/confirm` 把一条笔记升为「项目事实」（律师点一下）。
 * 写入侧仍在 AI 助手那边（回答下方的书签 → `POST /agent/memory/notes`，锚点由服务端按会话反查）。
 *
 * **为什么不复用 copilot 的 `AgentMemoryItem`**：那个类型是「助手记忆」管理面
 * （个人/团队/律所三级、可增删确认），本项目页只要内容/来源/锚点和确认动作。
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

/** 一页 50 条：够铺满抽屉，又不至于打开面板就拖一条长请求。同时是「加载更多」的步长 */
export const PROJECT_NOTES_PAGE_SIZE = 50

/** 分页参数：后端 `list_memories` 用 limit/offset 手推，返回条数 < limit 即末页 */
export interface ProjectNotesPage {
  limit?: number
  offset?: number
}

/** 本项目下的一页 AI 笔记（默认从第 0 条起的 50 条） */
export function listProjectNotes(contractId: number, page: ProjectNotesPage = {}): Promise<ProjectNote[]> {
  return agentApi
    .get('memory', {
      searchParams: {
        contract_id: contractId,
        limit: page.limit ?? PROJECT_NOTES_PAGE_SIZE,
        offset: page.offset ?? 0,
      },
    })
    .json<ProjectNote[]>()
}

/**
 * 把一条笔记升为「项目事实」——模型写的只是判断，必须由律师点一下才生效。
 *
 * `content` 只在律师改写时传：后端把「没传」当保留原文、把传值当改写，两者语义
 * 不能混（传空串不是「不改」）。改写上限由后端 `write.NOTE_MAX_CHARS` 把关，
 * 弹窗里先按同一上限拦一次。
 */
export function confirmProjectNote(noteId: string, content?: string): Promise<ProjectNote> {
  return agentApi.post(`memory/${noteId}/confirm`, { json: content ? { content } : {} }).json<ProjectNote>()
}
