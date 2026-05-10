import type { StateCreator, StoreApi } from 'zustand'
import type { BatchJobItem, BatchProgress } from '../types'
import * as api from '../api'
import { stripMetadataBlock } from './streaming-helpers'
import { createBatchItemMessage, createBatchSummaryMessage } from './message-factory'
import { formatBatchContent } from '../utils/format-batch'
import type { WorkbenchStore } from './workbench-store'

// 跟踪已展示的批量分析 item ID，避免重复注入消息
let _shownBatchItemIds: Set<string> = new Set()
// SSE 连接清理函数
let _cleanupBatchSSE: (() => void) | null = null

// ─── 共享辅助函数 ────────────────────────────────────────────────────────────

type SetFn = StoreApi<WorkbenchStore>['setState']
type GetFn = () => WorkbenchStore

function injectCompletedItem(
  get: GetFn,
  itemId: string, fileName: string, result: string, jobId: string,
) {
  if (_shownBatchItemIds.has(itemId)) return
  _shownBatchItemIds.add(itemId)
  get().appendMessages(createBatchItemMessage(fileName, formatBatchContent(stripMetadataBlock(result)), jobId))
}

async function handleTerminal(set: SetFn, get: GetFn, progress: BatchProgress) {
  set({ batchPolling: false } as Partial<WorkbenchStore>)

  const completedItems = progress.items.filter(
    (item) => item.status === 'completed' && item.result,
  )

  const { postAnalysisPrompt } = get()

  if (postAnalysisPrompt && completedItems.length > 0) {
    // 有后处理提示词：把所有分析结果 + 提示词发给主 AI
    const resultsText = completedItems
      .map((item) => `### ${item.file_name}\n\n${formatBatchContent(stripMetadataBlock(item.result))}`)
      .join('\n\n---\n\n')
    const summaryNote = progress.job.summary
      ? `\n\n---\n\n### 汇总报告\n\n${progress.job.summary}`
      : ''
    const message = `以下是批量文档分析的结果，请根据要求进行处理。\n\n${resultsText}${summaryNote}\n\n---\n\n**要求：**${postAnalysisPrompt}`

    set({ postAnalysisPrompt: '' } as Partial<WorkbenchStore>)
    // 清除进度卡片后发送给主 AI
    set({ batchProgress: null, activeBatchJobId: null } as Partial<WorkbenchStore>)
    await get().sendMessage(message)
    return
  }

  // 无后处理提示词：保持原有行为（持久化 batch 消息 + 下载 CSV）
  if (completedItems.length > 0) {
    try {
      await api.saveBatchMessages(
        progress.job.id,
        completedItems.map((item) => ({
          file_name: item.file_name,
          content: `### ${item.file_name}\n\n${formatBatchContent(stripMetadataBlock(item.result))}`,
          metadata: { source: 'batch_item', job_id: progress.job.id },
        })),
      )
    } catch { /* 持久化失败不影响用户体验 */ }
  }

  if (progress.job.status === 'completed' && progress.job.summary) {
    try {
      await api.saveBatchMessages(progress.job.id, [{
        file_name: '汇总报告',
        content: progress.job.summary,
        metadata: { source: 'batch_analysis', job_id: progress.job.id },
      }])
    } catch { /* 持久化失败不影响用户体验 */ }

    get().appendMessages(createBatchSummaryMessage(progress.job.summary, progress.job.id))
  }
}

function handleSSEEvent(set: SetFn, get: GetFn, event: { type: string; data: Record<string, unknown> }) {
  const { batchProgress } = get()
  if (!batchProgress) return

  if (event.type === 'item_started') {
    const itemId = event.data.item_id as string
    const fileName = event.data.file_name as string
    const bp = batchProgress
    const exists = bp.items.some((i) => i.id === itemId)
    if (!exists) {
      set({
        batchProgress: {
          ...bp,
          items: [...bp.items, {
            id: itemId,
            file_name: fileName,
            status: 'running',
            result: '',
            error: '',
            duration_ms: null,
          } as BatchJobItem],
        },
      })
    }
  } else if (event.type === 'item_completed' || event.type === 'item_failed') {
    const isCompleted = event.type === 'item_completed'
    const itemId = event.data.item_id as string
    const fileName = event.data.file_name as string
    const durationMs = event.data.duration_ms as number | undefined
    const error = event.data.error as string | undefined

    const bp = batchProgress
    const completed = isCompleted ? (bp.job.completed_items || 0) + 1 : (bp.job.completed_items || 0)
    const failed = !isCompleted ? (bp.job.failed_items || 0) + 1 : (bp.job.failed_items || 0)
    const total = bp.job.total_items || 1
    const progress = Math.round((completed + failed) * 100 / total)

    const existingIdx = bp.items.findIndex((i) => i.id === itemId)
    let items: BatchJobItem[]
    if (existingIdx >= 0) {
      items = bp.items.map((item, idx) =>
        idx === existingIdx
          ? { ...item, status: isCompleted ? 'completed' : 'failed', duration_ms: durationMs ?? item.duration_ms, error: error ?? item.error }
          : item,
      )
    } else {
      items = [...bp.items, {
        id: itemId,
        file_name: fileName,
        status: isCompleted ? 'completed' : 'failed',
        result: '',
        error: error ?? '',
        duration_ms: durationMs ?? null,
      } as BatchJobItem]
    }

    set({
      batchProgress: {
        ...bp,
        items,
        job: { ...bp.job, completed_items: completed, failed_items: failed, progress },
      },
    })
  } else if (event.type === 'progress') {
    const data = event.data
    set({
      batchProgress: {
        ...batchProgress,
        job: {
          ...batchProgress.job,
          completed_items: data.completed_items as number,
          failed_items: data.failed_items as number,
          total_items: data.total_items as number,
          progress: data.progress as number,
        },
      },
    })
  }
}

function startSSEConnection(
  set: SetFn,
  get: GetFn,
  jobId: string,
) {
  _cleanupBatchSSE = api.connectBatchSSE(
    jobId,
    (event) => {
      // setTimeout 脱离 React 批量更新，确保每个事件触发独立渲染
      setTimeout(() => handleSSEEvent(set, get, event), 0)
    },
    async () => {
      try {
        const progress = await api.getBatchProgress(jobId)
        set({ batchProgress: progress })
        for (const item of progress.items) {
          if (item.status === 'completed' && item.result) {
            injectCompletedItem(get, item.id, item.file_name, item.result, progress.job.id)
          }
        }
        await handleTerminal(set, get, progress)
      } catch {
        set({ batchPolling: false } as Partial<WorkbenchStore>)
      }
    },
    () => {
      _cleanupBatchSSE = null
      const poll = async () => {
        const { activeBatchJobId, batchPolling } = get()
        if (!activeBatchJobId || !batchPolling) return
        try {
          const progress = await api.getBatchProgress(activeBatchJobId)
          set({ batchProgress: progress })
          for (const item of progress.items) {
            if (item.status === 'completed' && item.result) {
              injectCompletedItem(get, item.id, item.file_name, item.result, progress.job.id)
            }
          }
          if (['completed', 'failed', 'cancelled'].includes(progress.job.status)) {
            await handleTerminal(set, get, progress)
            return
          }
        } catch { /* 轮询失败不停止 */ }
        const { batchProgress: bp } = get()
        const p = bp?.job.progress ?? 0
        const interval = p > 80 ? 5000 : 2000
        setTimeout(poll, interval)
      }
      setTimeout(poll, 2000)
    },
  )
}

// ─── Slice 定义 ──────────────────────────────────────────────────────────────

export interface BatchSlice {
  activeBatchJobId: string | null
  batchProgress: BatchProgress | null
  batchPolling: boolean
  postAnalysisPrompt: string
  submitBatchAnalysis: (prompt: string, files: File[], postAnalysisPrompt?: string) => Promise<void>
  cancelBatchAnalysis: () => Promise<void>
  dismissBatchProgress: () => void
  recoverActiveBatchJob: (sessionId: number) => Promise<void>
  resetBatch: () => void
}

export const createBatchSlice: StateCreator<WorkbenchStore, [], [], BatchSlice> = (set, get) => ({
  activeBatchJobId: null,
  batchProgress: null,
  batchPolling: false,
  postAnalysisPrompt: '',

  submitBatchAnalysis: async (prompt, files, postAnalysisPrompt = '') => {
    const { currentSession, selectedModel } = get()
    if (!currentSession) return

    if (_cleanupBatchSSE) {
      _cleanupBatchSSE()
      _cleanupBatchSSE = null
    }

    _shownBatchItemIds = new Set()
    const job = await api.submitBatchAnalysis(currentSession.id, prompt, selectedModel, files)
    set({
      activeBatchJobId: job.id,
      batchProgress: { job, items: [], failed_items_detail: [] },
      batchPolling: true,
      postAnalysisPrompt,
    })

    startSSEConnection(set, get, job.id)

    // 轮询获取文件列表（后端 task 启动后才会创建 BatchJobItem）
    const pollItems = async () => {
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 500))
        const { activeBatchJobId, batchProgress: bp } = get()
        if (!activeBatchJobId || activeBatchJobId !== job.id || !bp) return
        if (bp.items.length > 0) return // SSE 已经填充了 items
        try {
          const progress = await api.getBatchProgress(job.id)
          if (progress.items.length > 0) {
            set({ batchProgress: { ...bp, items: progress.items, failed_items_detail: progress.failed_items_detail } })
            return
          }
        } catch { /* ignore */ }
      }
    }
    pollItems()
  },

  cancelBatchAnalysis: async () => {
    const { activeBatchJobId } = get()
    if (!activeBatchJobId) return
    try {
      await api.cancelBatchAnalysis(activeBatchJobId)
    } catch { /* ignore */ }
  },

  dismissBatchProgress: () => {
    set({ batchProgress: null, activeBatchJobId: null })
  },

  recoverActiveBatchJob: async (sessionId) => {
    const { activeBatchJobId } = get()
    if (activeBatchJobId) return

    try {
      const res = await api.listBatchJobs(sessionId)
      const runningJob = res.items.find(
        (j) => j.status === 'running' || j.status === 'pending',
      )
      if (!runningJob) return

      const progress = await api.getBatchProgress(runningJob.id)
      set({
        activeBatchJobId: runningJob.id,
        batchProgress: progress,
        batchPolling: true,
      })

      for (const item of progress.items) {
        if (item.status === 'completed' && item.result) {
          injectCompletedItem(get, item.id, item.file_name, item.result, progress.job.id)
        }
      }

      startSSEConnection(set, get, runningJob.id)
    } catch { /* 恢复失败不影响正常使用 */ }
  },

  resetBatch: () => {
    cleanupBatchState()
    set({
      activeBatchJobId: null,
      batchProgress: null,
      batchPolling: false,
      postAnalysisPrompt: '',
    })
  },
})

export function cleanupBatchState(): void {
  if (_cleanupBatchSSE) {
    _cleanupBatchSSE()
    _cleanupBatchSSE = null
  }
  _shownBatchItemIds = new Set()
}
