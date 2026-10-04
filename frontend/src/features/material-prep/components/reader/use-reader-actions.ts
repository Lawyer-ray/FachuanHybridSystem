import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { countUnclassified, markAllSegsDone, resetSegments } from '../../draft'
import { useReader } from '../../store'
import type { DraftState, PageKey } from '../../types'
import { ZOOM_MAX, ZOOM_MIN, ZOOM_STEP } from './ui'

/**
 * 阅读器动作层：分段聚焦跳转、完成 / 重置分段、归档留痕、删页二次确认、缩放。
 * draft 为 null（未打开 / loading）时界面不渲染、动作不会被触发，内部按空值兜底。
 */
export function useReaderActions(draft: DraftState | null) {
  const openId = useReader((s) => s.openId)
  const zoom = useReader((s) => s.zoom)
  const [focusedSeg, setFocusedSeg] = useState(0)
  // 待确认删除的页（破坏性操作必须先经 AlertDialog 二次确认）
  const [deleteTarget, setDeleteTarget] = useState<PageKey[] | null>(null)

  // 换包重置聚焦段（与 Reader 内其余视图态的重置同一时机）
  useEffect(() => {
    setFocusedSeg(0)
  }, [openId])

  const focusSeg = (si: number) => {
    setFocusedSeg(si)
    requestAnimationFrame(() => {
      document.getElementById(`seg-${si}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  const zoomIn = () => useReader.getState().setZoom(Math.min(ZOOM_MAX, +(zoom + ZOOM_STEP).toFixed(2)))
  const zoomOut = () => useReader.getState().setZoom(Math.max(ZOOM_MIN, +(zoom - ZOOM_STEP).toFixed(2)))

  const onComplete = () => {
    if (!draft) return
    const allClassified = draft.segs.length > 0 && countUnclassified(draft) === 0
    if (!allClassified) {
      const first = draft.segs.findIndex((s) => !s.t)
      if (first >= 0) focusSeg(first)
      toast.info('还有未归类的段，先点段头的类型胶囊选一下')
      return
    }
    useReader.getState().update((d) => markAllSegsDone(d))
    toast.success(`拆分与归类完成 —— 共 ${draft.segs.length} 份材料`)
  }

  const onResetSegments = () => {
    if (!draft) return
    useReader.getState().update((d) => resetSegments(d))
    focusSeg(0)
    toast('已恢复初始分段 —— 每个源文件各一份')
  }

  const onReject = () => {
    useReader.getState().setStatus('filed')
    toast('已归档留痕，未建案')
    useReader.getState().close()
  }

  const confirmDelete = () => {
    if (deleteTarget?.length) {
      useReader.getState().deleteSelected(deleteTarget)
      toast(`已删除 ${deleteTarget.length} 页 —— 从材料拆分中移除`)
    }
    setDeleteTarget(null)
  }

  return {
    focusedSeg,
    focusSeg,
    deleteTarget,
    setDeleteTarget,
    zoomIn,
    zoomOut,
    onComplete,
    onResetSegments,
    onReject,
    confirmDelete,
  }
}
