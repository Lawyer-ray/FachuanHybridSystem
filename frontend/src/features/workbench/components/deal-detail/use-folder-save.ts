import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { downloadUrl } from '@/lib/download'
import { withDownloadTicket } from '@/lib/download-ticket'
import { folderFileUrl, type FolderOwnerKind } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { intentSubpath, useSaveAs } from './use-save-as'

/**
 * 文件夹文档的「保存 / 另存为 / 下载」三件套（整页预览 `FilePreview` 与右栏
 * 文档卡 `FilePreviewCard` 共用同一条 OnlyOffice 保存链路）。
 *
 * **为什么抽出来**：两个组件原先各自逐字复刻了这套逻辑（约 50 行 × 2），
 * 已经开始漂移——整页版的忙碌态多一个 `'download'` 档、页内版用独立
 * `downloading` 布尔。两页共用同一套 DS `forcesave` 回调落盘，任何一处改
 * 延迟刷新时长/toast 文案/失效 key 都要改两遍，漏一遍就静默不一致。
 *
 * **为什么保存只能走 forcesave**：社区版没有 `downloadAs`，外层拿不到文件
 * 字节（详见 `OfficeView` 的 `requestSave`）。编辑器把内容推回 callbackUrl，
 * 后端 `adopt_edited` 覆写原文件，所以这里既没有「上传」也没有即时成功反馈。
 *
 * 行为口径（刻意与原两处逐字对齐，勿改）：
 * - 保存提示「已提交保存 / 文档服务器正在写回原文件」；
 * - 落盘在 DS 回调里（通常 1–3 秒），**延迟 2500ms** 再刷两路：文件夹树
 *   （react-query 缓存 60s，不主动失效就一直旧）+ 父级 `onSaved`；
 * - 下载票据**一次性**，每次现换，不能缓存复用；
 * - 另存为「先登记意图 → 再 forcesave」：登记失败不保存，否则原稿被覆盖。
 */

/** 保存链路的忙碌态（`save`/`saveAs` 互斥；下载单独一档，见 `downloading`） */
export type FolderSaveBusy = 'save' | 'saveAs' | null

export function useFolderSave({
  kind,
  ownerId,
  file,
  requestSave,
  onSaved,
  canSave,
  saveAsEnabled,
  ready,
}: {
  kind: FolderOwnerKind
  ownerId: number
  file: { subpath: string; name: string }
  /** 触发 DS forcesave；编辑器未就绪返回 false */
  requestSave: () => boolean
  /** 保存成功后的延迟刷新回调（父级据此重取 mtime/大小等业务数据） */
  onSaved?: () => void
  /**
   * 是否允许原地保存（只有 docx）。
   *
   * 原两处在这里不一致：整页版 ⌘S 不判格式，只读文档上也会走一遍保存并弹
   * 「已提交保存」的假成功；页内版判了 `isDocx`。统一判 `canSave` 后两页
   * 一致，按钮/文案/请求都没变，只是不再给只读文档假成功提示。
   */
  canSave: boolean
  /** 是否开放「另存为」（只有合同文件夹的 docx 有 folder-save-as 端点） */
  saveAsEnabled: boolean
  /** 编辑器是否就绪（⌘S 只在就绪后触发） */
  ready: boolean
}): {
  /** 站内路径（不带票据）：DS 取文件走后端签名代理，这里只用来签配置 */
  fileUrl: string
  save: () => void
  saveAs: () => void
  download: () => Promise<void>
  busy: FolderSaveBusy
  downloading: boolean
} {
  const qc = useQueryClient()
  const fileUrl = folderFileUrl(kind, ownerId, file.subpath)
  const [busy, setBusy] = useState<FolderSaveBusy>(null)
  const [downloading, setDownloading] = useState(false)

  const save = useCallback(() => {
    if (busy !== null || !canSave) return
    setBusy('save')
    try {
      if (!requestSave()) {
        toast.error('编辑器尚未就绪，请稍后重试')
        return
      }
      toast.success('已提交保存', { description: '文档服务器正在写回原文件' })
      // 落盘发生在 DS 回调里，延迟刷新才能读到新 mtime
      window.setTimeout(() => {
        void qc.invalidateQueries({ queryKey: workbenchKeys.folderEntries(kind, ownerId) })
        onSaved?.()
      }, 2500)
    } finally {
      setBusy(null)
    }
  }, [busy, canSave, requestSave, onSaved, qc, kind, ownerId])

  /** 另存为：登记意图 → forcesave（登记失败不保存，否则会把原稿覆盖） */
  const runSaveAs = useSaveAs({
    kind,
    ownerId,
    file: { subpath: intentSubpath(kind, ownerId, file.subpath), name: file.name },
    requestSave,
    onSaved,
    enabled: saveAsEnabled,
    locked: busy !== null,
  })
  const saveAs = useCallback(() => {
    if (busy !== null || !saveAsEnabled) return
    setBusy('saveAs')
    try {
      // 登记接口是异步往返：先占住按钮防连点，错误由 useSaveAs 内部 toast 处理
      void runSaveAs().finally(() => setBusy(null))
    } catch {
      setBusy(null)
    }
  }, [busy, saveAsEnabled, runSaveAs])

  const download = useCallback(async () => {
    setDownloading(true)
    try {
      // 票据是一次性的：每次下载都要现换，不能缓存复用
      const url = await withDownloadTicket(fileUrl)
      downloadUrl(url, file.name)
    } finally {
      setDownloading(false)
    }
  }, [fileUrl, file.name])

  // ⌘S 保存是律师的肌肉记忆。用 ref 持最新回调：save 依赖 busy，直接入依赖
  // 会让监听每轮重装；document 上的监听换一次就等于一次摘挂。
  const saveRef = useRef(save)
  useEffect(() => {
    saveRef.current = save
  }, [save])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (ready && canSave) void saveRef.current()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [ready, canSave])

  return { fileUrl, save, saveAs, download, busy, downloading }
}
