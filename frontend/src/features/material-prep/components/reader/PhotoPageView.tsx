import { useEffect, useState } from 'react'
import { Image as ImageIcon } from 'lucide-react'

import { fetchAttachmentBytes } from '../../api'

export function PhotoPageView({ messageId, partIndex }: { messageId: number; partIndex: number }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let alive = true
    let objectUrl: string | null = null
    fetchAttachmentBytes(messageId, partIndex)
      .then((bytes) => {
        objectUrl = URL.createObjectURL(new Blob([bytes]))
        if (alive) setUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl) // 卸载后才回来：别漏 revoke
      })
      .catch(() => {
        // 加载失败要有可见反馈（与 PdfPageView 的 error 分支同款），不能静默吞掉
        if (alive) setError(true)
      })
    return () => {
      alive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [messageId, partIndex])

  if (error) {
    return (
      <div className="grid h-48 place-items-center text-xs text-muted-foreground">该页加载失败</div>
    )
  }
  if (!url) {
    return (
      <div className="grid h-56 place-items-center bg-zinc-50 text-xs text-muted-foreground">
        <ImageIcon className="h-6 w-6" />
      </div>
    )
  }
  return <img src={url} alt="材料页" className="block h-auto w-full bg-white" />
}
