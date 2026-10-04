import { useState } from 'react'
import { toast } from 'sonner'

import { confirmDates, revokeDate } from '../api'
import { selectedPendingRows, selectedTextRows, type CandidateRow } from '../domain'
import type { TaskOut } from '../types'
import { errMessage } from '@/lib/errors'

interface UseConfirmActionsArgs {
  isFileMode: boolean
  task: TaskOut | null
  rows: CandidateRow[]
  /** 全部写入成功后（含文件模式刷新完）由调用方刷新外部状态 */
  onSaved: () => void
  /** 文字模式全部写入后关闭弹窗 */
  onClose: () => void
  /** 文字模式：逐条 /reminders/create 的回调（由 home 注入，避免反向依赖） */
  onConfirmText?: (rows: CandidateRow[]) => Promise<number>
  /** 文件模式：写入后刷新任务态 */
  refresh: () => Promise<void>
}

/** 候选写入动作（文件 / 文字两条路径）+ 跳过 / 撤销，共用一个 busy 态。 */
export function useConfirmActions({ isFileMode, task, rows, onSaved, onClose, onConfirmText, refresh }: UseConfirmActionsArgs) {
  const [busy, setBusy] = useState(false)

  const doConfirm = async () => {
    if (busy) return
    const writableCount = isFileMode ? selectedPendingRows(rows).length : selectedTextRows(rows).length
    if (writableCount === 0) {
      toast.info('请先勾选要写入的日期')
      return
    }
    setBusy(true)
    try {
      if (isFileMode && task) {
        const items = selectedPendingRows(rows).map((r) => ({
          candidate_id: r.candidateId as number,
          action: 'confirm' as const,
          // datetime-local 原文（naive 本地）上送，服务端补时区——不能 toISOString
          due_at: r.dueLocal,
          reminder_type: r.reminderType,
        }))
        const res = await confirmDates(task.task_id, items)
        // 生成物里 results 是可选数组（后端异常路径可能缺省），按空处理
        const results = res.results ?? []
        const errors = results.filter((x) => x.status === 'error')
        if (errors.length) {
          toast.warning(`${errors.length} 条未写入：${errors[0]?.message ?? '未知原因'}`)
        } else {
          const reused = results.filter((x) => x.message.includes('复用')).length
          toast.success(`已写入 ${results.length} 条提醒${reused ? `（${reused} 条复用了既有提醒）` : ''}`)
        }
        await refresh()
        onSaved()
      } else if (onConfirmText) {
        const created = await onConfirmText(selectedTextRows(rows))
        toast.success(`已加入日历 ${created} 条`)
        onClose()
        onSaved()
      }
    } catch (e) {
      toast.error(errMessage(e, '写入失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  const doSkip = async (row: CandidateRow) => {
    if (!task || busy || row.candidateId == null) return
    setBusy(true)
    try {
      await confirmDates(task.task_id, [{ candidate_id: row.candidateId, action: 'skip' }])
      await refresh()
    } catch (e) {
      toast.error(errMessage(e, '操作失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  const doRevoke = async (row: CandidateRow) => {
    if (!task || busy || row.candidateId == null) return
    setBusy(true)
    try {
      await revokeDate(task.task_id, row.candidateId)
      toast.success('已撤销并删除该条提醒')
      await refresh()
      onSaved()
    } catch (e) {
      toast.error(errMessage(e, '撤销失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  return { busy, doConfirm, doSkip, doRevoke }
}
