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
}

export function OfficeView({
  fileUrl,
  fileName,
  mode = 'review',
  version = '',
}: {
  /** 站内下载路径（后端会为 DS 签发可重复使用的 HMAC 签名代理地址） */
  fileUrl: string
  fileName: string
  mode?: EditorMode
  version?: string
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
              if (!cancelled) setState('ready')
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
      if (inst?.destroyEditor) {
        try {
          inst.destroyEditor()
        } catch {
          // DS 已卸载时 destroy 会抛，忽略即可
        }
      }
    }
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
