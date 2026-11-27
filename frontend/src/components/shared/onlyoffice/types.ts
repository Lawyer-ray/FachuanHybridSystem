/**
 * OnlyOffice 编辑器对外的**公共契约**（handle / 插件桥消息 / 画布状态）。
 *
 * 从 `OfficeView.tsx` 拆出：这些类型被 2 个 feature 的 3 个文件深路径消费
 * （`contract-review/ReviewWorkbenchPage.tsx`、`workbench/FilePreviewCard.tsx`、
 * `workbench/use-live-rewrite-apply.ts`），而组件本体是 React 渲染 + DS 生命周期。
 * 「别人依赖的契约」和「本组件怎么实现的」不是一件事，混在一个文件里会让每次改渲染
 * 都看起来像动了公共 API。
 *
 * 兼容口径：`OfficeView.tsx` 仍 re-export 本文件的全部类型，既有 import 路径不变。
 * 新增消费方可以直接引本文件；由本文件反向引 `OfficeView.tsx` 则禁止（会成环）。
 */

export interface EditorInstance {
  destroyEditor?: () => void
  /** DS 官方：把当前编辑内容存为指定格式的 Blob。用于「保存 / 另存为」。 */
  downloadAs?: (format: string) => Promise<Blob>
  /**
   * DS 的外部命令入口（`serviceCommand({ c: 'forcesave' })` 触发立即回存）。
   *
   * 不在官方对外文档里，社区版实例上确实存在（实测）；声明成可选即表示
   * 「可能没有」，调用侧用 typeof 守卫——所以这里是类型而非断言。
   */
  serviceCommand?: (cmd: { c: string }) => void
}

/** 供调用方持有的编辑器句柄 */
export interface OfficeEditorHandle {
  /**
   * 触发编辑器内部保存（DS 工具栏的「保存」）。
   *
   * **为什么不是 `downloadAs('docx')` 取字节自己上传**：社区版的编辑器实例
   * 不暴露 `downloadAs`（实测 `Asc.editor` 上只有私有的 `forceSave*` 系列），
   * 外层也拿不到实例方法。而 DS 自带保存按钮会走 `forcesave` → 命中
   * `callbackUrl` → 后端 `adopt_edited` 落盘，这条链路是真的通的。
   *
   * 返回是否成功点到按钮（编辑器未就绪或 DOM 结构变化时返回 false）。
   */
  requestSave: () => boolean
  /**
   * 向文档内核发一条命令（协议见 deploy/onlyoffice/plugins 里 plugin.js）。
   *
   * 可用 action：`get-selection` / `insert-revision` / `locate` / `apply-revision` /
   * `accept-all` / `reject-all` / `add-comments` / `get-comments` / `capabilities`。
   * 回执统一从 `onPluginMessage` 回来（类型见 `PluginBridgeMessage`）。
   */
  sendToPlugin: (action: string, text?: string, payload?: Record<string, unknown>) => void
}

/** 批注回执里单条的定位结果 */
export interface PluginCommentResult {
  index: number
  ok: boolean
  reason?: string
  commentId?: string
}

/** 画布内已经存在的批注（`GetAllComments` 的归一化形态） */
export interface PluginComment {
  commentId: string
  quote: string
  text: string
  userName: string
  solved: boolean
}

/** 内核能力探测回执（决定「AI 署名分离」等分支走哪条路，不靠猜） */
export interface PluginCapabilities {
  assistantTrackRevisions?: boolean
  trackRevisions?: boolean
  contentControl?: boolean
}

/** 插件桥回传的消息（口径与 plugin.js 的 post({type:...}) 完全一致） */
export type PluginBridgeMessage =
  | { type: 'ready'; editorType?: string; supported?: boolean }
  | { type: 'selection'; text: string; explicit?: boolean }
  | { type: 'inserted'; text?: string; error?: string }
  | { type: 'located'; found?: boolean; result?: { ok: boolean } }
  | { type: 'applied'; result?: { ok: boolean; reason?: string; how?: string } }
  | { type: 'commented'; result?: { ok: boolean; reason?: string; results?: PluginCommentResult[] } }
  | { type: 'comments'; result?: { ok: boolean; reason?: string; comments?: PluginComment[] } }
  | { type: 'capabilities'; result?: PluginCapabilities & { ok?: boolean } }
  | { type: 'done'; error?: string }
  | { type: 'hello'; editorType?: string; supported?: boolean }

/** 发往插件的消息（页面 → 桥） */
export interface PluginBridgeOutgoing {
  source: 'fachuan-page'
  action: string
  text?: string
  payload?: Record<string, unknown>
}

/** 画布可见状态（父级据此把「正在打开」改成真话） */
export type EditorState = 'loading' | 'ready' | 'error' | 'disabled'
