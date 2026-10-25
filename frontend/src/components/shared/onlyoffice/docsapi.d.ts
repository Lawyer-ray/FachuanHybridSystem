/**
 * OnlyOffice Document Server 的全局类型声明。
 *
 * ## 为什么需要这个文件
 *
 * OnlyOffice 的 `api.js` 被加载后会在 `window` 上挂一个 `DocsAPI` 全局对象，
 * 它不是 npm 包、没有随包类型——TypeScript 默认不认识 `window.DocsAPI`，
 * `tsc -b` 会直接报 `Property 'DocsAPI' does not exist on type 'Window'`，
 * 把整个前端 build 卡死。
 *
 * 声明放在这里而不是写进 `OfficeView.tsx`：`window` 增强必须作用于全局，
 * 写在模块里对其它文件（包括测试）不生效；而测试里确实也要直接读写
 * `window.DocsAPI`（注入假的 DocEditor 断言行为）。
 *
 * ## 声明口径
 *
 * 只声明**法穿实际用到的部分**（构造器 + destroyEditor），不追求覆盖 DS 全量
 * API。声明得越窄，将来 DS 升级时的维护面越小；真需要新成员时在这里加一行
 * 即可，比 `any` 更安全——`any` 会让写错的方法名静默通过。
 */

/** DS 编辑器实例（法穿只用 destroy，其余交给 DS 自己）。 */
export interface OnlyOfficeEditorInstance {
  /** 卸载编辑器；部分 DS 版本没有该方法，所以可选。 */
  destroyEditor?: () => void
}

/** `new DocsAPI.DocEditor(id, config)` 的配置形状。 */
export interface OnlyOfficeConfig {
  document?: Record<string, unknown>
  editorConfig?: Record<string, unknown>
  documentType?: string
  width?: string
  height?: string
  events?: {
    onDocumentReady?: () => void
    onError?: (event: unknown, data: unknown) => void
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface OnlyOfficeApi {
  DocEditor: new (placeholderId: string, config: OnlyOfficeConfig) => OnlyOfficeEditorInstance
}

declare global {
  interface Window {
    /** 由 DS 的 `api.js` 注入；未加载完成时为 undefined。 */
    DocsAPI?: OnlyOfficeApi
  }
}

export {}
