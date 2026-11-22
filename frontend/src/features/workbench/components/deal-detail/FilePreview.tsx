import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, CopyPlus, Download, FileSearch, Loader2, Save } from 'lucide-react'

import { OfficeView, type OfficeEditorHandle } from '@/components/shared/onlyoffice/OfficeView'
import type { FolderOwnerKind } from '../../api'
import { canSaveAs } from './use-save-as'
import { useFolderSave } from './use-folder-save'
import { useLiveRewriteApply } from './use-live-rewrite-apply'
import { useFileRewriteNonce } from './use-rewrite-refresh'

/**
 * 合同文件夹里单个文件的预览 / 编辑视图（整页，不是抽屉）。
 *
 * **为什么整页**：初版是右侧窄抽屉 + 全屏暗遮罩。实际用起来两个问题：
 * 文档被挤在右侧、左边半屏被遮罩白占（看合同本就需要宽度）；半透明黑遮罩
 * 压在列表上很脏，像报错弹层而不是浏览文档。现在顶栏返回、中间整块给文档。
 *
 * **原地改、原地存**：律师看到错字想直接改，不必走一整轮 AI 审查。
 * - 保存：**原地覆盖**原文件——走 DS `forcesave` 回调落盘，后端
 *   `adopt_edited` 直接覆写，**不做 mtime 校验**（这次保存就是当前会话
 *   产生的，校验只会在「编辑器开着时文件被外部改」的少见场景误报，见后端
 *   domain_registry 注释）；
 * - 另存为：默认 `原名[修订版]V1_<今天>.docx`，写**新文件**、原文件不动。
 *   字节同样只在 DS 那边（社区版没有 `downloadAs`），所以顺序是「先登记
 *   一次性意图 → 再 forcesave」，回调按意图写新名字。
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
  const editorRef = useRef<OfficeEditorHandle | null>(null)
  const [ready, setReady] = useState(false)
  const isDocx = /\.docx$/i.test(file.name)
  // 另存为只对合同文件夹的 docx 开放（cases 没有 folder-save-as 系列端点）
  const saveAsEnabled = canSaveAs(kind, file.name)
  // AI 直改覆写该文件的次数：>0 时作为 version 换 key 重载画布，修订痕迹才可见
  const rewriteNonce = useFileRewriteNonce(kind, ownerId, file.subpath)
  // 就地落修订通道（合同/案件 docx 通用）：AI 覆写成功时免重载直接在画布里长出修订
  const liveApply = useLiveRewriteApply({
    enabled: isDocx,
    key: `${kind}:${ownerId}:${file.subpath}`,
  })

  /**
   * 触发保存（DS forcesave → 回调落盘）。
   *
   * 不走「取字节再上传」：社区版没有 `downloadAs`，外层拿不到内容。
   */
  const requestSave = useCallback((): boolean => {
    const h = editorRef.current
    return h ? h.requestSave() : false
  }, [])

  // 保存 / 另存为 / 下载：与右栏文档卡共用同一条 DS 保存链路（见 use-folder-save）
  const { fileUrl, save, saveAs, download, busy, downloading } = useFolderSave({
    kind,
    ownerId,
    file,
    requestSave,
    onSaved,
    canSave: isDocx,
    saveAsEnabled,
    ready,
  })

  // 键盘：⌘S 由 useFolderSave 接管；Esc 退出是整页预览独有的导航行为，留在本层
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && busy === null) onBack()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [busy, onBack])

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
          <button
            type="button"
            onClick={save}
            disabled={!ready || busy !== null || downloading}
            className="inline-flex h-[30px] flex-none items-center gap-1.5 rounded-[8px] bg-foreground px-3 text-[12px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-50"
            title="保存到原文件（⌘S）"
          >
            <Save className="size-3.5" />
            保存
          </button>
        )}

        {saveAsEnabled && (
          <button
            type="button"
            onClick={saveAs}
            disabled={!ready || busy !== null || downloading}
            className="inline-flex h-[30px] flex-none items-center gap-1.5 rounded-[8px] border border-border bg-card px-2.5 text-[12px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary disabled:opacity-50"
            title="另存为新文件（原名[修订版]V1_今天.docx），原文件不动"
          >
            {busy === 'saveAs' ? <Loader2 className="size-3.5 animate-spin" /> : <CopyPlus className="size-3.5" />}
            另存为
          </button>
        )}

        <button
          type="button"
          onClick={() => void download()}
          disabled={busy !== null || downloading}
          className="inline-flex h-[30px] flex-none items-center gap-1.5 rounded-[8px] border border-border bg-card px-2.5 text-[12px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary disabled:opacity-50"
        >
          {downloading ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
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
          version={rewriteNonce ? String(rewriteNonce) : ''}
          onEditorReady={(h) => {
            editorRef.current = h
            setReady(!!h)
            liveApply.onEditorReady(h)
          }}
        />
      </div>
    </div>
  )
}
