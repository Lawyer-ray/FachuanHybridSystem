import { useState } from 'react'
import { ExternalLink, FileText, Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'

interface Props {
  url: string
  className?: string
}

/** 文书原文预览栏：PDF 走 iframe（浏览器原生查看器），图片走 img。 */
export function DocumentPreview({ url, className }: Props) {
  const [loaded, setLoaded] = useState(false)
  const isImage = /\.(jpe?g|png)(\?|$)/i.test(url)
  return (
    <div className={cn('flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-border bg-secondary/30', className)}>
      <div className="flex flex-none items-center gap-2 border-b border-border bg-card px-3 py-2">
        <FileText className="h-3.5 w-3.5 flex-none text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-semibold text-muted-foreground">文书原文</span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex flex-none items-center gap-1 rounded-[6px] border border-border px-2 py-[3px] text-[10.5px] text-muted-foreground transition-colors hover:border-ring/40 hover:text-foreground"
        >
          <ExternalLink className="h-3 w-3" />
          新窗口
        </a>
      </div>
      <div className="relative min-h-0 flex-1">
        {!loaded && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
        {isImage ? (
          <img
            src={url}
            alt="文书原文"
            onLoad={() => setLoaded(true)}
            className="h-full w-full object-contain"
          />
        ) : (
          <iframe
            src={url}
            title="文书预览"
            onLoad={() => setLoaded(true)}
            className={cn('h-full w-full border-none transition-opacity duration-300', loaded ? 'opacity-100' : 'opacity-0')}
          />
        )}
      </div>
    </div>
  )
}
