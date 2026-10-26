/**
 * 引用来源卡（豆包式）：「引用」不再是一排零散 chip，而是一张有视觉锚点的卡。
 *
 * 两个消费面共用同一套语言（渐变左条 + 圆角图标位 + 标题/来源两行）：
 * - RefQuoteCard：MessageList 里 user 消息上方的**折叠卡**——单引用静态展示，
 *   多引用收起时只露首行 + 「共 N 个」徽标，展开列出全部（details/summary
 *   原生折叠，与 ToolRow/ThinkingBlock 同一交互习惯）
 * - QuoteChip：Composer 输入区待发引用/附件的迷你卡，带移除钮
 *
 * 主题仍守中性灰阶：渐变只用 primary 的同色系深浅，不做彩色渐变。
 */

import { ChevronDown, FileText, Folder, Paperclip, X } from 'lucide-react'

import type { RefOwnerKind } from '../types'

/** 引用来源的最小形状：SentRefMeta 与 FolderRefDraft 都满足（ownerId 等多出的字段无妨） */
export interface QuoteSource {
  kind: RefOwnerKind
  subpath: string
  name: string
  isFolder?: boolean
}

function kindLabel(kind: RefOwnerKind) {
  return kind === 'case' ? '案件' : '合同'
}

/** 渐变左条：卡的视觉锚点，标示「这是被引用进来的内容」 */
function QuoteStrip() {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute inset-y-[6px] left-0 w-[2.5px] rounded-r-full bg-gradient-to-b from-primary/80 via-primary/45 to-primary/10"
    />
  )
}

/** 圆角图标位：引用文件/目录在浅色 tint 里给一眼可辨的类型信号 */
function QuoteIcon({ source }: { source: QuoteSource }) {
  const Icon = source.isFolder ? Folder : FileText
  return (
    <span className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-[8px] bg-primary/10 text-primary">
      <Icon className="h-[15px] w-[15px]" />
    </span>
  )
}

/** 标题 + 来源两行（两处共用；meta 可换成附件的「大小」） */
function QuoteText({ source, meta }: { source: QuoteSource; meta?: string }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[12px] leading-[1.45] font-[600] text-foreground">
        {source.name}
        {source.isFolder ? '/' : ''}
      </span>
      <span className="block truncate text-[10.5px] leading-[1.45] text-muted-foreground">
        {meta ?? `${kindLabel(source.kind)}${source.isFolder ? '目录' : '文件'} · ${source.subpath}`}
      </span>
    </span>
  )
}

/** user 消息上方的引用卡：单引用静态，多引用可折叠（收起露首行 + 计数徽标） */
export function RefQuoteCard({ refs }: { refs: QuoteSource[] }) {
  const first = refs[0]
  if (!first) return null
  const row = (r: QuoteSource) => (
    <span className="flex min-w-0 items-center gap-2" title={`${kindLabel(r.kind)} ${r.subpath}${r.isFolder ? '（目录引用：AI 会先列出目录内容再按需读取）' : '（引用原文件，发送时由 AI 直接读取）'}`}>
      <QuoteIcon source={r} />
      <QuoteText source={r} />
    </span>
  )

  if (refs.length <= 1) {
    return (
      <div className="relative w-fit max-w-full rounded-[10px] border border-border bg-card py-1.5 pr-2.5 pl-3 shadow-sm">
        <QuoteStrip />
        {row(first)}
      </div>
    )
  }
  return (
    <details className="group/ref relative w-fit max-w-full rounded-[10px] border border-border bg-card shadow-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 py-1.5 pr-2 pl-3">
        <QuoteStrip />
        {row(first)}
        <span className="ml-0.5 flex-none rounded-full bg-primary/10 px-1.5 py-px text-[10px] leading-[1.5] font-[620] text-primary">
          共 {refs.length} 个
        </span>
        <ChevronDown className="h-3.5 w-3.5 flex-none text-muted-foreground transition-transform duration-200 group-open/ref:rotate-180" />
      </summary>
      <div className="border-t border-border-light py-1 pr-2.5 pl-3">
        {refs.map((r) => (
          <div key={`${r.kind}-${r.subpath}`} className="py-0.5">
            {row(r)}
          </div>
        ))}
      </div>
    </details>
  )
}

/** Composer 待发引用/附件的迷你卡：单行紧凑版，X 移除 */
export function QuoteChip({
  source,
  meta,
  icon,
  onRemove,
  removeLabel,
}: {
  source: QuoteSource
  /** 附件用「大小」替代路径 meta */
  meta?: string
  /** 上传附件用回形针与「引用」区分开；缺省按 source 类型取 */
  icon?: 'attachment'
  onRemove: () => void
  removeLabel: string
}) {
  return (
    <span className="relative flex max-w-full items-center gap-2 rounded-[9px] border border-border bg-card py-1 pr-1 pl-2.5 shadow-sm">
      <QuoteStrip />
      {icon === 'attachment' ? (
        <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-[7px] bg-secondary text-secondary-foreground">
          <Paperclip className="h-3 w-3" />
        </span>
      ) : (
        <QuoteIcon source={source} />
      )}
      <QuoteText source={source} meta={meta} />
      <button
        type="button"
        className="flex h-5 w-5 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-destructive"
        aria-label={removeLabel}
        onClick={onRemove}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}
