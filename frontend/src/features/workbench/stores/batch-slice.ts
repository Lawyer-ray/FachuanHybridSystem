import type { StateCreator, StoreApi } from 'zustand'
import type { BatchProgress } from '../types'
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
  set: SetFn,
  itemId: string, fileName: string, result: string, jobId: string,
) {
  if (_shownBatchItemIds.has(itemId)) return
  _shownBatchItemIds.add(itemId)
  set((state) => ({
    messages: [...state.messages, createBatchItemMessage(fileName, formatBatchContent(stripMetadataBlock(result)), jobId)],
  }))
}

async function handleTerminal(set: SetFn, progress: BatchProgress) {
  set({ batchPolling: false } as Partial<WorkbenchStore>)

  const completedItems = progress.items.filter(
    (item) => item.status === 'completed' && item.result,
  )
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

    set((state) => ({
      messages: [...state.messages, createBatchSummaryMessage(progress.job.summary, progress.job.id)],
      batchProgress: null,
    }))
  }
}

function handleSSEEvent(set: SetFn, get: GetFn, event: { type: string; data: Record<string, unknown> }) {
  const { batchProgress } = get()
  if (!batchProgress) return

  if (event.type === 'item_completed') {
    set({
      batchProgress: {
        ...batchProgress,
        job: { ...batchProgress.job, completed_items: (batchProgress.job.completed_items || 0) + 1 },
      },
    })
  } else if (event.type === 'item_failed') {
    set({
      batchProgress: {
        ...batchProgress,
        job: { ...batchProgress.job, failed_items: (batchProgress.job.failed_items || 0) + 1 },
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
    (event) => handleSSEEvent(set, get, event),
    async () => {
      try {
        const progress = await api.getBatchProgress(jobId)
        set({ batchProgress: progress })
        for (const item of progress.items) {
          if (item.status === 'completed' && item.result) {
            injectCompletedItem(set, item.id, item.file_name, item.result, progress.job.id)
          }
        }
        await handleTerminal(set, progress)
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
              injectCompletedItem(set, item.id, item.file_name, item.result, progress.job.id)
            }
          }
          if (['completed', 'failed', 'cancelled'].includes(progress.job.status)) {
            await handleTerminal(set, progress)
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
  submitBatchAnalysis: (prompt: string, files: File[]) => Promise<void>
  cancelBatchAnalysis: () => Promise<void>
  recoverActiveBatchJob: (sessionId: number) => Promise<void>
}

export const createBatchSlice: StateCreator<WorkbenchStore, [], [], BatchSlice> = (set, get) => ({
  activeBatchJobId: null,
  batchProgress: null,
  batchPolling: false,

  submitBatchAnalysis: async (prompt, files) => {
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
    })

    startSSEConnection(set, get, job.id)
  },

  cancelBatchAnalysis: async () => {
    const { activeBatchJobId } = get()
    if (!activeBatchJobId) return
    try {
      await api.cancelBatchAnalysis(activeBatchJobId)
    } catch { /* ignore */ }
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
          injectCompletedItem(set, item.id, item.file_name, item.result, progress.job.id)
        }
      }

      startSSEConnection(set, get, runningJob.id)
    } catch { /* 恢复失败不影响正常使用 */ }
  },
})

export function cleanupBatchState(): void {
  if (_cleanupBatchSSE) {
    _cleanupBatchSSE()
    _cleanupBatchSSE = null
  }
  _shownBatchItemIds = new Set()
}
