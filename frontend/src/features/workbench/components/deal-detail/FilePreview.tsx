import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Download, FileSearch, Loader2, Save } from 'lucide-react'
import { toast } from 'sonner'

import { OfficeView, type OfficeEditorHandle } from '@/components/shared/onlyoffice/OfficeView'
import { withDownloadTicket } from '@/lib/download-ticket'
import { defaultSaveAsName } from './save-as-name'
import {
  folderFileUrl,
  saveFolderFile,
  saveFolderFileAs,
  type FolderOwnerKind,
} from '../../api'

/**
 * 合同文件夹里单个文件的预览 / 编辑视图（整页，不是抽屉）。
 *
 * **为什么整页**：初版是右侧窄抽屉 + 全屏暗遮罩。实际用起来两个问题：
 * 文档被挤在右侧、左边半屏被遮罩白占（看合同本就需要宽度）；半透明黑遮罩
 * 压在列表上很脏，像报错弹层而不是浏览文档。现在顶栏返回、中间整块给文档。
 *
 * **原地改、原地存**：律师看到错字想直接改，不必走一整轮 AI 审查。
 * - 保存：覆盖原文件（`saveFolderFile`），带 mtime 乐观锁防并发覆盖；
 * - 另存为：默认 `原名[修订版]V1_<今天>.docx`，不动原文件。
 *
 * 两条路都**不保留备份**（产品决定）：覆盖即覆盖，版本追溯走审查链路的
 * `DocumentVersion`，不靠磁盘上的历史目录。
 */
export function FilePreview({
  kind,
  ownerId,
  file,
  onBack,
  onReview,
  onSaved,
}: {
  kind: FolderOwnerKind
  ownerId: number
  file: { subpath: string; name: string; mtime?: number }
  onBack: () => void
  onReview?: (f: { subpath: string; name: string }) => void
  /** 保存/另存为成功后回调（父级据此刷新文件夹列表） */
  onSaved?: () => void
}) {
  /** 站内路径（不带票据）：DS 取文件走后端签名代理，这里只用来签配置 */
  const fileUrl = folderFileUrl(kind, ownerId, file.subpath)
  const editorRef = useRef<OfficeEditorHandle | null>(null)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState<'save' | 'save-as' | 'download' | null>(null)
  /** 打开时的 mtime，保存时带上做乐观锁 */
  const openedMtime = file.mtime
  const isDocx = /\.docx$/i.test(file.name)

  const getBytes = useCallback(async (): Promise<Blob | null> => {
    const h = editorRef.current
    if (!h) return null
    return h.getDocxBlob()
  }, [])

  const save = useCallback(async () => {
    if (busy) return
    setBusy('save')
    try {
      const blob = await getBytes()
      if (!blob) {
        toast.error('编辑器尚未就绪，请稍后重试')
        return
      }
      await saveFolderFile(kind, ownerId, file.subpath, blob, openedMtime)
      toast.success('已保存到原文件', { description: file.name })
      onSaved?.()
    } catch (e) {
      const msg = e instanceof Error ? e.message : '保存失败'
      // 409 = mtime 不一致（别人改过），要说清楚而不是笼统「失败」
      toast.error(msg.includes('409') || msg.includes('他人修改') ? '文件已被他人修改' : msg, {
        description: msg.includes('409') || msg.includes('他人修改') ? '请返回重新打开后再改' : undefined,
      })
    } finally {
      setBusy(null)
    }
  }, [busy, getBytes, kind, ownerId, file.subpath, file.name, openedMtime, onSaved])

  const saveAs = useCallback(async () => {
    if (busy) return
    const suggested = defaultSaveAsName(file.name)
    const name = window.prompt('另存为（同目录，不会覆盖原文件）', suggested)
    if (!name || !name.trim()) return

    setBusy('save-as')
    try {
      const blob = await getBytes()
      if (!blob) {
        toast.error('编辑器尚未就绪，请稍后重试')
        return
      }
      const out = await saveFolderFileAs(kind, ownerId, file.subpath, name.trim(), blob)
      toast.success('已另存为 ' + out.name)
      onSaved?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '另存失败')
    } finally {
      setBusy(null)
    }
  }, [busy, getBytes, kind, ownerId, file.subpath, file.name, onSaved])

  const download = useCallback(async () => {
    setBusy('download')
    try {
      // 票据是一次性的：每次下载都要现换，不能缓存复用
      const url = await withDownloadTicket(fileUrl)
      const a = document.createElement('a')
      a.href = url
      a.download = file.name
      a.rel = 'noopener'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } finally {
      setBusy(null)
    }
  }, [fileUrl, file.name])

  // 键盘：⌘S 保存是律师的肌肉记忆；Esc 退出。
  // 用 ref 持最新回调，避免把 save 放进依赖造成 memo 环路（它依赖 busy）。
  const saveRef = useRef(save)
  useEffect(() => {
    saveRef.current = save
  }, [save])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (ready && !busy) void saveRef.current()
        return
      }
      if (e.key === 'Escape' && !busy) onBack()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [ready, busy, onBack])

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col bg-secondary/40">
      {/* 顶栏：返回 + 文件名 + 操作。不用遮罩，用实体工具条分隔 */}
      <div className="flex flex-none items-center gap-2 border-b border-border bg-card px-4 py-2.5">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex h-[30px] flex-none items-center gap-1 rounded-[8px] px-2 text-[12.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
        >
          <ArrowLeft className="size-3.5" />
          合同文件夹
        </button>

        <div className="mx-1 h-4 w-px flex-none bg-border" aria-hidden />

        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-[650]" title={file.name}>
            {file.name}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {ready ? '可直接编辑 · ⌘S 保存到原文件' : '正在打开文档…'}
          </p>
        </div>

        {isDocx && (
          <>
            <button
              type="button"
              onClick={() => void saveAs()}
              disabled={!ready || busy !== null}
              className="inline-flex h-[30px] flex-none items-center gap-1.5 rounded-[8px] border border-border bg-card px-2.5 text-[12px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary disabled:opacity-50"
            >
              {busy === 'save-as' ? <Loader2 className="size-3.5 animate-spin" /> : null}
              另存为
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={!ready || busy !== null}
              className="inline-flex h-[30px] flex-none items-center gap-1.5 rounded-[8px] bg-foreground px-3 text-[12px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-50"
            >
              {busy === 'save' ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
              保存
            </button>
          </>
        )}

        <button
          type="button"
          onClick={() => void download()}
          disabled={busy !== null}
          className="inline-flex h-[30px] flex-none items-center gap-1.5 rounded-[8px] border border-border bg-card px-2.5 text-[12px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary disabled:opacity-50"
        >
          {busy === 'download' ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
          下载
        </button>

        {onReview && isDocx && (
          <button
            type="button"
            onClick={() => onReview({ subpath: file.subpath, name: file.name })}
            className="inline-flex h-[30px] flex-none items-center gap-1.5 rounded-[8px] border border-border bg-card px-2.5 text-[12px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
          >
            <FileSearch className="size-3.5" />
            AI 审查
          </button>
        )}
      </div>

      {/* 文档占满剩余空间：OnlyOffice 自带分页与缩放，别再额外挤压 */}
      <div className="min-h-0 flex-1 bg-[#f6f6f7]">
        <OfficeView
          fileUrl={fileUrl}
          fileName={file.name}
          mode={isDocx ? 'edit' : 'view'}
          onEditorReady={(h) => {
            editorRef.current = h
            setReady(!!h)
          }}
        />
      </div>
    </div>
  )
}
