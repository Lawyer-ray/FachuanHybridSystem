import { useCallback, useEffect, useRef, useState } from 'react'
import { CopyPlus, Download, FileSearch, Loader2, Maximize2, Minimize2, Save, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'

import {
  OfficeView,
  type EditorState,
  type OfficeEditorHandle,
  type PluginBridgeMessage,
} from '@/components/shared/onlyoffice/OfficeView'
import { prefillCopilot, quoteCopilot } from '@/features/copilot/launch'
import { formatBytes } from '@/lib/format'
import { folderFileUrl, type FolderOwnerKind } from '../../api'
import { FileKindChip } from './FileKindBadge'
import { canSaveAs } from './use-save-as'
import { useFolderSave } from './use-folder-save'
import { useCanvasPresence } from './use-canvas-presence'
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
 *
 * **尺寸由父级给**：本组件只管「吃掉剩余高度」，画布高度/宽度归 DealDocLayout
 * 的四种文档态决定（在右侧栏时 720px 宽就够，沉浸态要占满整宽）。
 */
export function FilePreviewCard({
  kind,
  ownerId,
  file,
  onClose,
  onSaved,
  onReview,
  immersive = false,
  onToggleImmersive,
  onDirtyChange,
}: {
  kind: FolderOwnerKind
  ownerId: number
  file: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }
  onClose: () => void
  /** 保存成功后回调（父级据此刷新列表的 mtime/大小） */
  onSaved?: () => void
  /** 「AI 审查」——仅 docx（流水线只吃 docx） */
  onReview?: (f: { subpath: string; name: string }) => void
  /** 当前是否沉浸态（由父级持有状态） */
  immersive?: boolean
  /** 传了才渲染「沉浸编辑」按钮；不传说明该页不提供这档 */
  onToggleImmersive?: () => void
  /**
   * 画布里的改动有没有保存（父级据此在关闭/换文件前拦一下）。
   *
   * 以前这里是空白：律师改了半小时，随手点 X 或点另一份文件，改动就没了，
   * 而且全程零提示。
   */
  onDirtyChange?: (dirty: boolean) => void
}) {
  const [ready, setReady] = useState(false)
  /** 画布改动未保存（DS `onDocumentStateChange`） */
  const [dirty, setDirty] = useState(false)
  /** 画布状态：用来把底部那句「正在打开文档…」改成真话 */
  const [editorState, setEditorState] = useState<EditorState>('loading')
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
    // 就地落笔成功后要拿它登记「画布已同步」，口径与签配置的 file_url 逐字一致
    fileUrl: folderFileUrl(kind, ownerId, file.subpath),
  })
  // 告诉后端「这份文件的画布开着」：AI 写完盘据此决定要不要下发画布重放
  useCanvasPresence(kind, ownerId, file.subpath, isDocx)

  /** 编辑器句柄：保存时用 downloadAs 取当前内容 */
  const editorRef = useRef<OfficeEditorHandle | null>(null)

  /**
   * 关页签/刷新的最后一道提醒。
   *
   * 卡内关闭与换文件走确认弹窗，但直接关浏览器页签是拦不住的，只能靠原生提示。
   * 卸载时把「脏」告诉父级：否则文档被别的路径关掉后，页面还一直以为有未保存改动。
   */
  useEffect(() => {
    if (!dirty) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])
  // 回调身份每轮都在变（父级传的是内联箭头），用 ref 让「卸载时告诉父级已不再脏」
  // 只需挂一次；写进依赖的话，父级每次重渲都会跑一遍 cleanup，脏标记被清没。
  const onDirtyChangeRef = useRef(onDirtyChange)
  useEffect(() => {
    onDirtyChangeRef.current = onDirtyChange
  }, [onDirtyChange])
  useEffect(() => () => onDirtyChangeRef.current?.(false), [])

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

  // 保存 / 另存为 / 下载（含 ⌘S）：与整页预览共用同一条 DS 保存链路
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

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[10px] border border-border bg-card">
      {/* 头部：类型 + 文件名 + 操作 + 关闭 */}
      {/* flex-wrap：面板最窄可拖到 320px，纯 flex 会让末尾的「沉浸/关闭」被
          overflow-hidden 裁掉（点不到也看不见）。换行至少还都在 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border-light px-3 py-2">
        <FileKindChip name={file.name} />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-[620]" title={file.name}>
          {file.name}
        </span>
        {/* 未保存标记：没有它就只能靠「刚才好像改过」的记忆 */}
        {dirty && (
          <span
            className="flex-none rounded-[5px] border border-status-yellow/40 bg-status-yellow/10 px-1.5 text-[10.5px] font-[620] text-status-yellow"
            title="画布里有未保存的修改（⌘S 或「保存」写回原文件）"
          >
            未保存
          </span>
        )}

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

        {onToggleImmersive && (
          <button
            type="button"
            aria-label={immersive ? '退出沉浸' : '沉浸编辑'}
            onClick={onToggleImmersive}
            title={immersive ? '退出沉浸，回到对照视图' : '沉浸编辑：文档占满整宽与一屏高'}
            aria-pressed={immersive}
            className="grid size-6 flex-none place-items-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            {immersive ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>
        )}

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
          onStateChange={setEditorState}
          onDirtyChange={(d) => {
            setDirty(d)
            onDirtyChangeRef.current?.(d)
          }}
          onPluginMessage={(m: PluginBridgeMessage) => {
            // 只关心「选区」：插件在律师框选后推送，宿主把它变成指令。
            // 其余类型（ready/inserted/applied）由上层按需处理，这里不转发。
            if (m.type !== 'selection') return
            const sel = m.text.trim()
            // 点了「AI 改写」但没框选：原先静默丢弃，看着像按钮坏了
            if (!sel) {
              if (m.explicit) toast.info('先在文档里框选要改写的条款')
              return
            }

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
        {file.size ? <span>· {formatBytes(file.size)}</span> : null}
        {isDocx && (
          <span className={editorState === 'error' ? 'ml-auto text-status-yellow' : 'ml-auto'}>
            {editorState === 'error'
              ? '打开失败 · 可在画布里重试'
              : editorState === 'disabled'
                ? 'OnlyOffice 未启用，暂时无法编辑'
                : ready
                  ? '可直接编辑 · ⌘S 保存到原文件'
                  : '正在打开文档…'}
          </span>
        )}
      </div>
    </div>
  )
}
