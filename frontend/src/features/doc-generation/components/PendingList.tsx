import { Copy, Crosshair } from 'lucide-react'
import { toast } from 'sonner'

import { copyText } from '@/lib/clipboard'

/**
 * 未决项清单：起草时既没有素材、模型也没写出来的槽。
 *
 * **为什么每条都能复制槽名**：槽名就是骨架模板里的占位符名，律师照着它去
 * 补正文、或给 AI 下指令说「把 {{court_name}} 补上」才对得上位置；手抄一遍
 * 必然会错一个字符，然后整条指令失效。复制失败不能假装成功（内网 http 部署
 * 下 navigator.clipboard 是 undefined，兜底走 execCommand）。
 *
 * 清单本身不持有文档位置信息，`onLocate` 由调用方给——没有画布上下文时
 * （如 toast 里）就只留复制。
 */
export function PendingList({
  pending,
  onLocate,
}: {
  pending: string[]
  /** 可选：把光标定位到文档里该槽的位置（调用方有画布才传） */
  onLocate?: (slotKey: string) => void
}) {
  if (pending.length === 0) return null
  return (
    <ul className="mt-1.5 flex flex-col gap-1 text-[12px] leading-[1.6]">
      {pending.map((key) => (
        <li key={key} className="flex items-center gap-1.5">
          <code className="min-w-0 flex-1 truncate rounded bg-secondary px-1.5 py-0.5 text-[11.5px]">{key}</code>
          <button
            type="button"
            aria-label={`复制槽名 ${key}`}
            title="复制槽名（骨架模板里的占位符名）"
            className="inline-flex flex-none items-center gap-1 rounded px-1 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={() => {
              void copyText(key).then((ok) => {
                if (ok) toast.success('已复制槽名：' + key)
                else toast.error('复制失败，请手动选中槽名')
              })
            }}
          >
            <Copy className="size-3" />
            复制
          </button>
          {onLocate && (
            <button
              type="button"
              aria-label={`定位 ${key}`}
              className="inline-flex flex-none items-center gap-1 rounded px-1 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              onClick={() => onLocate(key)}
            >
              <Crosshair className="size-3" />
              定位
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}
