import { useEffect, useRef, useState } from 'react'
import { loadDocSpaceSDK, isDocSpaceSDKLoaded } from '@/lib/docspace-sdk'

interface DocSpaceFrameProps {
  /** DocSpace 文件 ID */
  fileId: number
  /** DocSpace Portal URL */
  portalUrl: string
  /** 编辑模式 */
  mode?: 'editor' | 'viewer'
  /** 关闭编辑器时的回调 */
  onClose?: () => void
  /** 自定义 class */
  className?: string
}

/**
 * 嵌入 OnlyOffice DocSpace 编辑器/预览器。
 * 动态加载 SDK，通过 iframe 渲染。
 */
export function DocSpaceFrame({
  fileId,
  portalUrl,
  mode = 'editor',
  onClose,
  className,
}: DocSpaceFrameProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        await loadDocSpaceSDK(portalUrl)
        if (cancelled || !containerRef.current) return

        if (!window.DocSpace?.SDK) {
          throw new Error('DocSpace SDK 未就绪')
        }

        window.DocSpace.SDK.initEditor({
          frameId: containerRef.current.id,
          src: portalUrl,
          id: String(fileId),
          width: '100%',
          height: '100%',
          type: mode === 'viewer' ? 'embedded' : 'desktop',
          editorCustomization: {
            goback: false,
          },
          events: {
            onAppReady: () => {
              if (!cancelled) setLoading(false)
            },
            onEditorCloseCallback: () => {
              onClose?.()
            },
            onAppError: (err: unknown) => {
              if (!cancelled) setError(String(err))
            },
          },
        })
      } catch (err) {
        if (!cancelled) setError(String(err))
      }
    }

    init()
    return () => { cancelled = true }
  }, [fileId, portalUrl, mode, onClose])

  const frameId = `docspace-frame-${fileId}`

  return (
    <div className={className} style={{ position: 'relative', width: '100%', height: '100%' }}>
      {loading && !error && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
          <span className="text-muted-foreground animate-pulse">加载编辑器中…</span>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
          <span className="text-destructive">加载失败: {error}</span>
        </div>
      )}
      <div
        ref={containerRef}
        id={frameId}
        style={{ width: '100%', height: '100%', minHeight: 500 }}
      />
    </div>
  )
}
