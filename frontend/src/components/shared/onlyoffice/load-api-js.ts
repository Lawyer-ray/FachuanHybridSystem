/**
 * 加载 OnlyOffice Document Server 的 `api.js`（全页只该加载一次）。
 *
 * 与 `OfficeView.tsx` 拆开的原因：这段是**进程级单例**（`apiScriptPromise` 让并发
 * 挂载共用一次 `<script>` 注入），与组件实例、props、渲染都无关。放在组件文件里时，
 * 读代码的人会以为它是某次渲染的一部分。
 *
 * 语义一个字都没改：`window.DocsAPI` 已在就直接 resolve；失败时把 Promise 置空，
 * 让下一次挂载能重试（不置空会让一次网络抖动永久卡死后继所有打开）。
 */

const API_JS = '/web-apps/apps/api/documents/api.js'


/** DS 的 api.js 全局只该加载一次：并发挂载时共用一个 Promise */
let apiScriptPromise: Promise<void> | null = null

export function loadApiJs(docserverUrl: string): Promise<void> {
  if (window.DocsAPI) return Promise.resolve()
  if (apiScriptPromise) return apiScriptPromise
  apiScriptPromise = new Promise<void>((resolve, reject) => {
    const el = document.createElement('script')
    el.src = `${docserverUrl.replace(/\/$/, '')}${API_JS}`
    el.async = true
    el.onload = () => resolve()
    el.onerror = () => {
      apiScriptPromise = null
      reject(new Error('OnlyOffice api.js 加载失败'))
    }
    document.head.appendChild(el)
  })
  return apiScriptPromise
}
