import { useState, useRef, useEffect } from 'react'

interface DocSpaceFrameProps {
  /** DocSpace 文件 ID */
  fileId: number
  /** DocSpace 编辑器 URL（从 API 返回的 webUrl） */
  editorUrl: string
  /** 关闭编辑器时的回调 */
  onClose?: () => void
  /** 自定义 class */
  className?: string
}

/**
 * 嵌入 OnlyOffice DocSpace 编辑器/预览器。
 * 直接用 iframe 加载编辑器 URL，不依赖 DocSpace JS SDK。
 */
export function DocSpaceFrame({
  editorUrl,
  onClose,
  className,
}: DocSpaceFrameProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [loaded, setLoaded] = useState(false)

  // 监听 iframe 内部消息（DocSpace 编辑器关闭时会 postMessage）
  useEffect(() => {
    function handleMessage(e: MessageEvent) {
      if (typeof e.data === 'string') {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'onEventReturn' && data.eventReturnData?.event === 'onEditorCloseCallback') {
            onClose?.()
          }
        } catch {
          // ignore non-JSON messages
        }
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [onClose])

  return (
    <div className={className} style={{ position: 'relative', width: '100%', height: '100%' }}>
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
          <span className="text-muted-foreground animate-pulse">加载编辑器中…</span>
        </div>
      )}
      <iframe
        ref={iframeRef}
        src={editorUrl}
        style={{ width: '100%', height: '100%', minHeight: 500, border: 'none' }}
        onLoad={() => setLoaded(true)}
        allow="clipboard-read; clipboard-write"
      />
    </div>
  )
}
