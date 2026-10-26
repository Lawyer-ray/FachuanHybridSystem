import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, TriangleAlert } from 'lucide-react'
import { getEditorConfig, type EditorMode } from './api'

/**
 * OnlyOffice Document Server 渲染单个文件。
 *
 * 与 PDF/图片走完全不同的路径：PDF 用 pdf.js 逐页渲染（可拆页），
 * Office 文档是**整份**交给 DS 渲染——docx 本身没有「页」这一层语义，
 * 自己排版必然失真（编号、样式、页眉页脚全是 DS 的活）。
 *
 * 配置由后端签发（见 ./api.ts）：前端只拿到
 * 已签名的 config，DS 的 JWT 密钥不出后端。
 */

const API_JS = '/web-apps/apps/api/documents/api.js'


let ooSeq = 0

/** DS 的 api.js 全局只该加载一次：并发挂载时共用一个 Promise */
let apiScriptPromise: Promise<void> | null = null

function loadApiJs(docserverUrl: string): Promise<void> {
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

interface EditorInstance {
  destroyEditor?: () => void
  /** DS 官方：把当前编辑内容存为指定格式的 Blob。用于「保存 / 另存为」。 */
  downloadAs?: (format: string) => Promise<Blob>
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
}

export function OfficeView({
  fileUrl,
  fileName,
  mode = 'review',
  version = '',
  onEditorReady,
}: {
  /** 站内下载路径（后端会为 DS 签发可重复使用的 HMAC 签名代理地址） */
  fileUrl: string
  fileName: string
  mode?: EditorMode
  version?: string
  /**
   * 编辑器就绪时交出句柄，供父级取内容（保存 / 另存为）。
   *
   * 只在本层拿得到 DS 实例（DocEditor 在这一层创建），因此必须往外递，
   * 否则父级只能猜字节。传 null 表示编辑器已销毁。
   */
  onEditorReady?: (handle: OfficeEditorHandle | null) => void
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<EditorInstance | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error' | 'disabled'>('loading')
  const [reason, setReason] = useState('')
  /** 挂载轮次：DS 首挂偶发「无报错但 iframe 不创建」，换 key 重挂即好 */
  const [attempt, setAttempt] = useState(0)
  /** 已成功挂载的签名：React StrictMode 会 effect→cleanup→effect，
   *  不加这层会把刚创建的实例立刻 destroy 掉，表现为「一直转圈」 */
  const mountedSig = useRef('')
  /** 当前 effect 的签名，cleanup 用它判断是否是被同一签名重新挂载 */
  const sigRef = useRef('')
  /** 挂载点 DOM id：DS 官方签名是 DocEditor(placeholderId, config)，传元素在部分版本静默失败 */
  const placeId = useMemo(() => `oo-${++ooSeq}`, [])

  useEffect(() => {
    let cancelled = false
    let deadTimer: ReturnType<typeof setTimeout> | null = null

    async function boot() {
      const sig = `${fileUrl}|${fileName}|${mode}|${version}|${attempt}`
      sigRef.current = sig
      mountedSig.current = sig
      setState('loading')
      setReason('')
      try {
        const payload = await getEditorConfig(fileUrl, fileName, mode, version)
        if (cancelled) return

        if (!payload.enabled || !payload.config) {
          setState('disabled')
          setReason(payload.reason || 'OnlyOffice 未启用')
          return
        }

        await loadApiJs(payload.docserver_url)
        if (cancelled || !hostRef.current) return

        // DS 会整体替换挂载节点内容：每次重建前先清空，避免残留旧实例
        hostRef.current.innerHTML = ''
        const inner = document.createElement('div')
        inner.id = placeId
        inner.style.width = '100%'
        inner.style.height = '100%'
        hostRef.current.appendChild(inner)

        const DocsAPI = window.DocsAPI
        if (!DocsAPI) throw new Error('DocsAPI 未就绪')

        editorRef.current = new DocsAPI.DocEditor(placeId, {
          ...payload.config,
          width: '100%',
          height: '100%',
          events: {
            onDocumentReady: () => {
              if (deadTimer) clearTimeout(deadTimer)
              if (!cancelled) {
                setState('ready')
                // 交出句柄：父级保存时调 downloadAs('docx') 取当前内容。
                // 用 ref 里的实例而不是闭包捕获，避免重挂后指向已销毁的旧实例。
                // 诊断用：暴露实例方法名（仅开发期需要，保留无害）
                onEditorReady?.({
                  requestSave: () => {
                    // DS 官方外部 API：serviceCommand({c:'forcesave'}) 让编辑器
                    // 立即把当前内容推回 callbackUrl（后端 adopt_edited 落盘）。
                    // 跨源时外层仍持有实例引用，方法调用不受同源限制——这是
                    // 唯一能「程序化触发保存」的正规入口（downloadAs 社区版没有）。
                    const inst = editorRef.current as unknown as
                      | { serviceCommand?: (a: { c: string }) => void }
                      | null
                    if (typeof inst?.serviceCommand !== 'function') return false
                    inst.serviceCommand({ c: 'forcesave' })
                    return true
                  },
                })
              }
            },
            onError: (_event: unknown, data: unknown) => {
              if (cancelled) return
              const d = data as { errorDescription?: string; error?: string } | undefined
              setState('error')
              setReason(d?.errorDescription || d?.error || '编辑器加载失败')
            },
          },
        })

        // 僵死探活：DS 偶发「DocEditor 调用无异常、回调不来、iframe 也不出现」
        // （原型阶段实测，社区版 9.4）。6 秒内宿主内仍无 iframe 就重建，最多 3 次。
        deadTimer = setTimeout(() => {
          if (cancelled) return
          const hasFrame = !!hostRef.current?.querySelector('iframe')
          if (hasFrame) return
          if (attempt < 3) {
            setAttempt((n) => n + 1)
          } else {
            setState('error')
            setReason('编辑器无响应（Document Server 未创建画布），请确认服务状态后重试')
          }
        }, 6000)
      } catch (err) {
        if (cancelled) return
        setState('error')
        setReason(err instanceof Error ? err.message : String(err))
      }
    }

    void boot()

    return () => {
      cancelled = true
      if (deadTimer) clearTimeout(deadTimer)
      const inst = editorRef.current
      editorRef.current = null
      // 告诉父级句柄失效：否则它在编辑器已销毁后调 downloadAs 会静默失败
      onEditorReady?.(null)
      if (inst?.destroyEditor) {
        try {
          inst.destroyEditor()
        } catch {
          // DS 已卸载时 destroy 会抛，忽略即可
        }
      }
    }
    // onEditorReady 有意不入依赖：调用方常传内联箭头，入依赖会让 effect
    // 每次渲染都重挂编辑器（画布反复重建）。它只是回调出口，换了也不需要重挂。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileUrl, fileName, mode, version, attempt, placeId])

  return (
    <div className="relative h-full w-full">
      <div ref={hostRef} className="h-full w-full" />

      {state === 'loading' && (
        <div className="absolute inset-0 grid place-items-center bg-white">
          <div className="flex flex-col items-center gap-2.5">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
            <p className="text-xs text-muted-foreground">正在打开文档…</p>
          </div>
        </div>
      )}

      {(state === 'error' || state === 'disabled') && (
        <div className="absolute inset-0 grid place-items-center bg-white px-8">
          <div className="flex max-w-sm flex-col items-center gap-2.5 text-center">
            <TriangleAlert className="size-5 text-status-yellow" />
            <p className="text-sm font-medium">
              {state === 'disabled' ? 'OnlyOffice 未启用' : '文档打开失败'}
            </p>
            <p className="text-[11.5px] leading-relaxed text-muted-foreground">{reason}</p>
          </div>
        </div>
      )}
    </div>
  )
}
