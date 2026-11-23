import { Copy } from 'lucide-react'
import { toast } from 'sonner'

import { copyText } from '@/lib/clipboard'

/** 行内复制按钮：点击复制并 toast */
export function CopyButton({ title, getText }: { title: string; getText: () => string }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      className="mt-0.5 flex size-6 flex-none items-center justify-center rounded-[7px] text-muted-foreground/50 opacity-60 transition-all hover:bg-foreground hover:text-background hover:opacity-100"
      onClick={(e) => {
        e.stopPropagation()
        const text = getText()
        void copyText(text).then(() => {
          toast.success('已复制：' + (text.split('\n')[0]?.replace(/（.*?）/, '').trim() ?? ''))
        })
      }}
    >
      <Copy className="size-3" />
    </button>
  )
}
