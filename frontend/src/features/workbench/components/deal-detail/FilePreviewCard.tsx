import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CopyPlus, Download, FileSearch, Loader2, Save, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'

import { OfficeView, type OfficeEditorHandle, type PluginBridgeMessage } from '@/components/shared/onlyoffice/OfficeView'
import { prefillCopilot, quoteCopilot } from '@/features/copilot/launch'
import { downloadUrl } from '@/lib/download'
import { withDownloadTicket } from '@/lib/download-ticket'
import { folderFileUrl, type FolderOwnerKind } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { FileKindChip } from './FileKindBadge'
import { fmtSize } from './folder-tree-types'
import { canSaveAs, intentSubpath, useSaveAs } from './use-save-as'
import { useLiveRewriteApply } from './use-live-rewrite-apply'
import { useFileRewriteNonce } from './use-rewrite-refresh'

/**
 * 右栏文档卡：**docx 直接可编辑，原地改原地存**，不跳页。
 *
 * **为什么不跳整页编辑器**：律师看合同几乎总要先对照左栏的服务事项、右栏的
 * 期限/当事人；跳走就断了对照。实测在 4K 屏上右栏拉宽后编辑体验与整页无差别，
 * 而「原地」省掉的是一次路由往返和一次上下文重建。
 *
 * **只读兜底**：pdf / 图片等不可编辑格式仍走 `view`，避免 OnlyOffice 把它们
 * 当可改文档打开（改完也存不回去）。
 */
export function FilePreviewCard({
  kind,
  ownerId,
  file,
  onClose,
  onSaved,
  onReview,
}: {
  kind: FolderOwnerKind
  ownerId: number
  file: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }
  onClose: () => void
  /** 保存成功后回调（父级据此刷新列表的 mtime/大小） */
  onSaved?: () => void
  /** 「AI 审查」——仅 docx（流水线只吃 docx） */
  onReview?: (f: { subpath: string; name: string }) => void
}) {
  const [downloading, setDownloading] = useState(false)
  const [busy, setBusy] = useState<'save' | 'saveAs' | null>(null)
  const [ready, setReady] = useState(false)
  const qc = useQueryClient()
  const fileUrl = folderFileUrl(kind, ownerId, file.subpath)
  const isDocx = /\.docx$/i.test(file.name)
  // 另存为只对合同文件夹的 docx 开放（cases 没有 folder-save-as 系列端点）
  const saveAsEnabled = canSaveAs(kind, file.name)
  // AI 直改覆写该文件的次数：>0 时作为 version 换 key 重载画布（DS 才会
  // 拉到已覆写的内容，修订痕迹可见）；未被覆写保持空串不动存量 key 口径
  const rewriteNonce = useFileRewriteNonce(kind, ownerId, file.subpath)
  // 就地落修订通道：AI 覆写成功时优先走插件桥在当前画布里直接长出修订
  // 痕迹（免整页重载），失败才轮到上面的 nonce 重载。合同与案件的 docx
  // 都注册（rewrite_folder_file 已支持两个绑定文件夹）
  const liveApply = useLiveRewriteApply({
    enabled: isDocx,
    key: `${kind}:${ownerId}:${file.subpath}`,
  })

  /** 编辑器句柄：保存时用 downloadAs 取当前内容 */
  const editorRef = useRef<OfficeEditorHandle | null>(null)

  /**
   * 触发保存。
   *
   * 走 DS 自己的 forcesave：编辑器把当前内容推回 callbackUrl，后端
   * `adopt_edited` 覆写到原文件。**不是**外层取字节再上传——社区版没有
   * `downloadAs`，取不到内容；而 forcesave 这条链路是真通的。
   *
   * 代价：没有即时成功反馈（落盘发生在回调里）。所以提示语是「正在保存」，
   * 并短暂延迟后再让父级刷新列表。
   */
  const requestSave = useCallback((): boolean => {
    const h = editorRef.current
    if (!h) return false
    return h.requestSave()
  }, [])

  /**
   * 「AI 改写」按钮：把编辑器当前选区送进右侧常驻助手。
   *
   * 选区只能由插件桥取（DS 内核上下文），这里发 `get-selection` 让插件读一次。
   * 插件回的 `selection` 消息会走 onPluginMessage 里的同一段逻辑，
   * 所以两条入口（按钮 / 框选自动）最终行为完全一致。
   *
   * 助手上下文随 kind 走（合同文件进合同会话、案件文件进案件会话）；
   * 框选提问与 AI 落笔直改（rewrite_folder_file）对两类文件都开放。
   */
  const rewriteSelection = useCallback(() => {
    const h = editorRef.current
    if (!h) {
      toast.error('编辑器尚未就绪，请稍后重试')
      return
    }
    // 先直接打开助手：即使插件桥没握手，律师也能在对话框里贴文字，
    // 而不是点了按钮没任何反馈。
    prefillCopilot('', {
      origin: kind === 'case' ? 'case' : 'contract',
      refId: ownerId,
      title: file.name.replace(/\.docx$/i, ''),
    })
    h.sendToPlugin('get-selection')
  }, [file.name, kind, ownerId])

  const save = useCallback(() => {
    if (busy || !isDocx) return
    setBusy('save')
    try {
      if (!requestSave()) {
        toast.error('编辑器尚未就绪，请稍后重试')
        return
      }
      toast.success('已提交保存', { description: '文档服务器正在写回原文件' })
      // 落盘发生在 DS 回调里（通常 1–3 秒），延迟刷新才能读到新 mtime。
      // 两路都刷：文件夹树（react-query 缓存 60s，不主动失效就一直旧）+
      // 父级详情（onSaved 刷新大小/日期等业务数据）
      window.setTimeout(() => {
        void qc.invalidateQueries({ queryKey: workbenchKeys.folderEntries(kind, ownerId) })
        onSaved?.()
      }, 2500)
    } finally {
      setBusy(null)
    }
  }, [busy, isDocx, requestSave, onSaved, qc, kind, ownerId])

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
    if (busy || !saveAsEnabled) return
    setBusy('saveAs')
    try {
      // 登记接口是异步往返：先占住按钮防连点，错误由 useSaveAs 内部提示
      void runSaveAs().finally(() => setBusy(null))
    } catch {
      setBusy(null)
    }
  }, [busy, saveAsEnabled, runSaveAs])

  const download = useCallback(async () => {
    setDownloading(true)
    try {
      // 票据一次性：每次下载现换，不能缓存复用
      const url = await withDownloadTicket(fileUrl)
      downloadUrl(url, file.name)
    } finally {
      setDownloading(false)
    }
  }, [fileUrl, file.name])

  // ⌘S 保存：律师的肌肉记忆，在编辑器里按一直是这个动作
  const saveRef = useRef(save)
  useEffect(() => {
    saveRef.current = save
  }, [save])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (isDocx && ready) void saveRef.current()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [isDocx, ready])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[10px] border border-border bg-card">
      {/* 头部：类型 + 文件名 + 操作 + 关闭 */}
      <div className="flex items-center gap-2 border-b border-border-light px-3 py-2">
        <FileKindChip name={file.name} />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-[620]" title={file.name}>
          {file.name}
        </span>

        {isDocx && (
          <>
            <button
              type="button"
              onClick={save}
              disabled={!ready || busy !== null}
              className="inline-flex h-[26px] flex-none items-center gap-1 rounded-[6px] bg-foreground px-2.5 text-[11.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-50"
              title="保存到原文件（⌘S）"
            >
              {busy === 'save' ? <Loader2 className="size-3 animate-spin" /> : <Save className="size-3" />}
              保存
            </button>

            {saveAsEnabled && (
              <button
                type="button"
                onClick={saveAs}
                disabled={!ready || busy !== null}
                className="inline-flex h-[26px] flex-none items-center gap-1 rounded-[6px] border border-border bg-card px-2 text-[11.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary disabled:opacity-50"
                title="另存为新文件（原名[修订版]V1_今天.docx），原文件不动"
              >
                {busy === 'saveAs' ? <Loader2 className="size-3 animate-spin" /> : <CopyPlus className="size-3" />}
                另存为
              </button>
            )}
          </>
        )}

        {onReview && isDocx && (
          <button
            type="button"
            onClick={() => onReview({ subpath: file.subpath, name: file.name })}
            className="inline-flex h-[26px] flex-none items-center gap-1 rounded-[6px] border border-border bg-card px-2 text-[11.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
          >
            <FileSearch className="size-3" />
            AI 审查
          </button>
        )}

        {/*
          「AI 改写」：常驻且**永远可见**的入口。

          为什么不只依赖框选自动触发：插件桥是幕后桥（无 UI），bridge 握手失败时
          界面上没有任何可点的地方，律师只能干看着——这个按钮是兵底。
          点它 → 读当前选区 → 调起右侧助手；没选区则提示先框选。
        */}
        {isDocx && (
          <button
            type="button"
            disabled={!ready}
            onClick={() => void rewriteSelection()}
            className="inline-flex h-[26px] flex-none items-center gap-1 rounded-[6px] border border-border bg-card px-2 text-[11.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary disabled:opacity-50"
            title="框选条款后点这里，或在文档里框选后右键「✦ AI 改写」"
          >
            <Sparkles className="size-3" />
            AI 改写
          </button>
        )}

        <button
          type="button"
          onClick={() => void download()}
          disabled={downloading}
          aria-label="下载"
          title="下载到本地"
          className="grid size-6 flex-none place-items-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
        >
          {downloading ? <Loader2 className="size-3 animate-spin" /> : <Download className="size-3.5" />}
        </button>

        <button
          type="button"
          aria-label="收起"
          onClick={onClose}
          className="grid size-6 flex-none place-items-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>

      {/* 画布：吃掉剩余高度，docx 直接进编辑态 */}
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
          onPluginMessage={(m: PluginBridgeMessage) => {
            // 只关心「选区」：插件在律师框选后推送，宿主把它变成指令。
            // 其余类型（ready/inserted/applied）由上层按需处理，这里不转发。
            if (m.type !== 'selection') return
            const sel = m.text.trim()
            if (!sel) return

            // 豆包式引用（不灌模板文字、不弹对话框）：选区挂成输入框上方的
            // 引用卡，输入框保持空白，律师自由提问或点快捷 pills。旧做法把
            // 「请按我的要求改写……修改要求：」整段塞进输入框，等于替律师
            // 打了一半草稿，他还得先删改才能问别的。kind 与 RefOwnerKind
            // 同构（contract/case），案件文书同样能框选提问与 AI 直改。
            quoteCopilot(
              {
                kind,
                ownerId,
                subpath: file.subpath,
                name: file.name,
                text: sel,
              },
              {
                origin: kind === 'case' ? 'case' : 'contract',
                refId: ownerId,
                title: file.name.replace(/\.docx$/i, ''),
              },
            )
          }}
        />
      </div>

      {/* 底部：元信息 + 可编辑提示 */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-border-light px-3 py-1.5 text-[11px] text-muted-foreground">
        {file.modified_at && <span className="tabular-nums">{file.modified_at.slice(0, 10)}</span>}
        {file.size ? <span>· {fmtSize(file.size)}</span> : null}
        {isDocx && <span className="ml-auto">{ready ? '可直接编辑 · ⌘S 保存到原文件' : '正在打开文档…'}</span>}
      </div>
    </div>
  )
}
