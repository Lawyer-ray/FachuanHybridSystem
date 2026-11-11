/**
 * 面板拖拽投放（双通道）：内部拖拽（目录树 → 输入区）走自定义 MIME
 * （FOLDER_REF_MIME）成引用；系统外文件走原生 Files 通道进上传流。
 * 浮层面板（CopilotPanel）使用。
 *
 * dragenter/over 必须 preventDefault 才能触发 drop；计数器法处理子元素
 * 间的 enter/leave 抖动。流式/上传在途不收件（与回形针按钮同口径）。
 */

import { useRef } from 'react'

import { FOLDER_REF_MIME, type FolderRefDraft } from '../types'
import { useCopilot } from '../store'

function dropAllowed(): boolean {
  const { streaming, uploadingAttachments } = useCopilot.getState()
  return !(streaming || uploadingAttachments)
}

export function useCopilotDrop() {
  const addAttachmentFiles = useCopilot((s) => s.addAttachmentFiles)
  const addFolderRef = useCopilot((s) => s.addFolderRef)
  const dragDepth = useRef(0)

  // dragover 对两条通道都要 preventDefault——drop 事件只有在 dragover
  // 「允许投放」时才会派发，漏掉自定义 MIME 会让引用拖放静默失效
  // （此前正是只拦了 Files）。高亮层仍只在 Files 通道出现（引用拖入的
  // 反馈是 Composer 里立即出现的引用 chip）。
  const droppable = (types: readonly string[]): boolean =>
    types.includes('Files') || types.includes(FOLDER_REF_MIME)

  const onDragEnter = (e: React.DragEvent) => {
    if (!droppable(e.dataTransfer?.types ?? [])) return
    e.preventDefault()
    if (!e.dataTransfer.types.includes('Files') || !dropAllowed()) return
    dragDepth.current += 1
    if (!useCopilot.getState().draggingFiles) useCopilot.setState({ draggingFiles: true })
  }
  const onDragOver = (e: React.DragEvent) => {
    if (!droppable(e.dataTransfer?.types ?? [])) return
    e.preventDefault()
  }
  const onDragLeave = (e: React.DragEvent) => {
    if (!e.dataTransfer?.types?.includes('Files')) return
    e.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) useCopilot.setState({ draggingFiles: false })
  }
  const onDrop = (e: React.DragEvent) => {
    // 无条件 preventDefault + 复位：拖文件夹（files 为空列表）或非文件投放，
    // 既不能让浏览器直接打开被拖入的文件，也不能让高亮层残留
    e.preventDefault()
    dragDepth.current = 0
    useCopilot.setState({ draggingFiles: false })
    // 内部拖拽（目录树 → 输入区）：自定义 MIME 携带引用，优先于 Files 通道
    const raw = e.dataTransfer.getData(FOLDER_REF_MIME)
    if (raw) {
      if (!dropAllowed()) return
      try {
        // 兼容两种 payload 形态：
        //   新 {kind, ownerId}（拖拽源已统一为此形态）
        //   旧 {contractId} / {caseId}（早期拖拽源遗留，或外部插件手拼）
        // 旧形态本身没有 kind 字段，所以必须由「是哪个 id 字段」反推 kind——
        // 此前只认 d.kind，旧 payload 会在下面的 kind 守卫处被静默丢弃，
        // 与本函数注释声称的「兼容」不符（回归用例见 use-copilot-drop.dom.test.tsx）。
        const d = JSON.parse(raw) as Partial<FolderRefDraft> & { contractId?: number; caseId?: number }
        // 显式 kind 优先；缺失时按 legacy 字段反推，两者都无则判为不可识别
        const kind =
          d.kind === 'case' || d.kind === 'contract'
            ? d.kind
            : typeof d.caseId === 'number'
              ? 'case'
              : typeof d.contractId === 'number'
                ? 'contract'
                : null
        const ownerId =
          kind === 'case' ? d.caseId ?? d.ownerId : d.contractId ?? d.ownerId
        if (kind && typeof ownerId === 'number' && typeof d.subpath === 'string' && d.subpath) {
          addFolderRef({
            kind,
            ownerId,
            subpath: d.subpath,
            name: String(d.name ?? ''),
            ...(d.isFolder ? { isFolder: true } : {}),
          })
        }
      } catch {
        // 非法 JSON 静默丢弃：不当作文件处理，也不打断 drop
      }
      return
    }
    if (!e.dataTransfer?.files?.length || !dropAllowed()) return
    addAttachmentFiles(e.dataTransfer.files)
  }

  return { onDragEnter, onDragOver, onDragLeave, onDrop }
}
