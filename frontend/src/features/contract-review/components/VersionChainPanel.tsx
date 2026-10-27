import { GitBranch } from 'lucide-react'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import type { DocumentVersion, VersionKind } from '../types'

/**
 * 版本链面板：这份合同改过几轮、每轮谁改的、从哪一版改出来的。
 *
 * 以前这些信息只活在文件名里（`[修订版]V1_日期` / `-律编v2`）：改名就断链，
 * 排序只对同一天有效，也看不出「客户回稿是接在哪一版后面的」。后端现在把
 * 每次产出挂成链上节点（parent 指向改自的那版），这里按序号展示。
 *
 * 不做交互式切换（点某版看内容）：那需要后端支持按版本取文件，属于下一步；
 * 现在先把「有过哪几版」讲清楚，比让律师去翻文件夹靠文件名猜强。
 */

/**
 * 版本来源 → 语义色档。用 Tone 而非各写一套 class：同一「谁改的」语义
 * （客户=待处理黄 / AI=进行中蓝 / 律师=完成绿）在别的列表里也是同一档色彩。
 */
const KIND_TONE: Record<VersionKind, Tone> = {
  original: 'neutral',
  ai: 'blue',
  lawyer: 'green',
  client: 'yellow',
}

export function VersionChainPanel({
  items,
  isLoading,
  error,
}: {
  items: DocumentVersion[]
  isLoading: boolean
  error: string | null
}) {
  if (isLoading) {
    return <LoadingBlock text="加载版本链…" size="sm" className="justify-start px-3.5 py-3" />
  }
  if (error) {
    return <div className="px-3.5 py-3 text-[11.5px] text-destructive">{error}</div>
  }
  if (items.length === 0) {
    return (
      <EmptyBlock className="items-start px-3.5 py-3 text-left leading-relaxed">
        还没有版本记录。审查跑完后会在这里出现「客户来稿 → AI 修订版」；
        你在编辑器里保存一次，就会多一个「律师编辑版」。
      </EmptyBlock>
    )
  }

  return (
    <div className="min-h-0 overflow-y-auto px-3 py-2">
      {items.map((v, i) => (
        <div key={v.id} className="relative flex gap-2.5 pb-2.5">
          {/* 连接线：最后一节不画，避免尾巴悬空 */}
          {i < items.length - 1 && (
            <span className="absolute left-[7px] top-4 h-full w-px bg-border-light" aria-hidden />
          )}
          <span className="relative z-10 mt-1 size-[15px] flex-none rounded-full border border-border bg-card" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[12px] font-[620]">V{v.version_no}</span>
              <StatusBadge tone={KIND_TONE[v.kind] ?? 'neutral'} size="xs">
                {v.kind_label}
              </StatusBadge>
              {v.author && <span className="truncate text-[10.5px] text-muted-foreground">{v.author}</span>}
            </div>
            <p className="mt-0.5 truncate text-[11px] text-secondary-foreground" title={v.file_name}>
              {v.file_name || '（文件已清理）'}
            </p>
            {v.note && <p className="mt-0.5 text-[10.5px] text-muted-foreground">{v.note}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

/** 版本链入口按钮（放在页头，点开右侧面板） */
export function VersionChainButton({ count, onClick }: { count: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-border bg-card px-2.5 text-[11.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary"
    >
      <GitBranch className="size-3.5" />
      版本链{count > 0 ? ` · ${count}` : ''}
    </button>
  )
}
