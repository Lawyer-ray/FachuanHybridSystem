import type { StateCreator } from 'zustand'
import type { BatchProgress } from '../types'
import * as api from '../api'
import { stripMetadataBlock } from './streaming-helpers'
import { createBatchItemMessage, createBatchSummaryMessage } from './message-factory'
import type { WorkbenchStore } from './workbench-store'

// 跟踪已展示的批量分析 item ID，避免重复注入消息
let _shownBatchItemIds: Set<string> = new Set()
// SSE 连接清理函数
let _cleanupBatchSSE: (() => void) | null = null

export interface BatchSlice {
  activeBatchJobId: string | null
  batchProgress: BatchProgress | null
  batchPolling: boolean
  submitBatchAnalysis: (prompt: string, files: File[]) => Promise<void>
  cancelBatchAnalysis: () => Promise<void>
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

    const handleTerminal = async (progress: BatchProgress) => {
      set({ batchPolling: false })

      const completedItems = progress.items.filter(
        (item) => item.status === 'completed' && item.result,
      )
      if (completedItems.length > 0) {
        try {
          await api.saveBatchMessages(
            progress.job.id,
            completedItems.map((item) => ({
              file_name: item.file_name,
              content: `### ${item.file_name}\n\n${stripMetadataBlock(item.result)}`,
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

    const injectCompletedItem = (itemId: string, fileName: string, result: string, jobId: string) => {
      if (_shownBatchItemIds.has(itemId)) return
      _shownBatchItemIds.add(itemId)
      set((state) => ({ messages: [...state.messages, createBatchItemMessage(fileName, stripMetadataBlock(result), jobId)] }))
    }

    _cleanupBatchSSE = api.connectBatchSSE(
      job.id,
      (event) => {
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
      },
      async () => {
        try {
          const progress = await api.getBatchProgress(job.id)
          set({ batchProgress: progress })
          for (const item of progress.items) {
            if (item.status === 'completed' && item.result) {
              injectCompletedItem(item.id, item.file_name, item.result, progress.job.id)
            }
          }
          await handleTerminal(progress)
        } catch {
          set({ batchPolling: false })
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
                injectCompletedItem(item.id, item.file_name, item.result, progress.job.id)
              }
            }
            if (['completed', 'failed', 'cancelled'].includes(progress.job.status)) {
              await handleTerminal(progress)
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
  },

  cancelBatchAnalysis: async () => {
    const { activeBatchJobId } = get()
    if (!activeBatchJobId) return
    try {
      await api.cancelBatchAnalysis(activeBatchJobId)
    } catch { /* ignore */ }
  },
})

export function cleanupBatchState(): void {
  if (_cleanupBatchSSE) {
    _cleanupBatchSSE()
    _cleanupBatchSSE = null
  }
  _shownBatchItemIds = new Set()
}
