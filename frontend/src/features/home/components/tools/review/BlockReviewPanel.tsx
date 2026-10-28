import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, HelpCircle, ScanText } from 'lucide-react'

import { cn } from '@/lib/utils'

import { ROW_BTN } from '../../../ui'
import type { ParseBlock, ParseCoverage } from '../../../api'
import {
  REVIEW_THRESHOLD,
  type ReviewFilter,
  canAttachConfidence,
  filterBlocks,
  formatConfidence,
  groupByPage,
  isBodyBlock,
  needsReview,
  reviewHeadline,
  reviewStats,
  scoreState,
} from './review-domain'

/**
 * 块级可信度复核面板。
 *
 * 设计原则（全部源自「别替沉默背书」这一条）：
 *  1. **未评估 ≠ 高分**。三态各自有独立颜色与文案，未评估用中性灰打问号，
 *     绝不用绿色——否则等于用 UI 保证内容正确，而实际上没人看过。
 *  2. **未评估不自动进「需复核」清单**。否则引擎一不支持打分整页全红，
 *     用户会训练出「红色可以无视」的习惯，这个功能就废了。
 *  3. **默认只显示正文**。页眉页脚页码常整段重复，混进来会把有限注意力稀释掉。
 *  4. 头部摘要如实说明「有几块未评估」，而不是笼统说「解析完成」。
 */

/** 单块的状态徽标 */
function ScoreBadge({ block }: { block: ParseBlock }) {
  const state = scoreState(block)
  if (state === 'unscored') {
    return (
      <span
        className="flex flex-none items-center gap-1 rounded-[6px] border border-border bg-secondary px-1.5 py-[1px] text-[10px] font-medium text-muted-foreground"
        title="当前引擎未提供该块的可信度，无法判断对错"
      >
        <HelpCircle className="h-2.5 w-2.5" />
        未评估
      </span>
    )
  }
  if (state === 'risky') {
    return (
      <span
        className="flex flex-none items-center gap-1 rounded-[6px] border border-status-red/40 bg-status-red-bg px-1.5 py-[1px] text-[10px] font-semibold text-status-red"
        title={`置信度 ${formatConfidence(block.confidence)}，低于阈值 ${REVIEW_THRESHOLD}`}
      >
        <AlertTriangle className="h-2.5 w-2.5" />
        {formatConfidence(block.confidence)}
      </span>
    )
  }
  return (
    <span
      className="flex flex-none items-center gap-1 rounded-[6px] border border-status-green/40 bg-status-green-bg px-1.5 py-[1px] text-[10px] font-semibold text-status-green"
      title={`置信度 ${formatConfidence(block.confidence)}`}
    >
      <CheckCircle2 className="h-2.5 w-2.5" />
      {formatConfidence(block.confidence)}
    </span>
  )
}

/** 块类型标签（表格/公式等非纯文本块要能一眼认出，内容展示形态不同） */
const TYPE_LABEL: Record<string, string> = {
  title: '标题',
  table: '表格',
  image: '图片',
  formula: '公式',
  header: '页眉',
  footer: '页脚',
}

function BlockRow({ block, dimmed }: { block: ParseBlock; dimmed?: boolean }) {
  const observed = needsReview(block)
  return (
    <div
      className={cn(
        'flex items-start gap-2 border-b border-border/60 px-3 py-2 last:border-b-0',
        // 需复核的行整体染成极浅红底，配合徽标让人不必逐行读文字
        observed && 'bg-status-red-bg/40',
        dimmed && 'opacity-55',
      )}
    >
      <ScoreBadge block={block} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          {TYPE_LABEL[block.type] && (
            <span className="flex-none text-[9.5px] font-semibold tracking-wide text-muted-foreground">
              {TYPE_LABEL[block.type]}
            </span>
          )}
          <span className="min-w-0 flex-1 text-[11.5px] leading-[1.6] whitespace-pre-wrap break-all text-foreground">
            {/* 图片块可能无文本，兜底给个占位而不是空白行 */}
            {block.text || (block.type === 'image' ? '（图片，无文本）' : '（空块）')}
          </span>
        </div>
        {block.review_reason && (
          <div className="mt-0.5 text-[10px] leading-snug text-status-red">{block.review_reason}</div>
        )}
      </div>
    </div>
  )
}

/** 单页容器（可折叠；默认展开有风险的页） */
function PageSection({ pageNo, blocks }: { pageNo: number | null; blocks: ParseBlock[] }) {
  const stats = reviewStats(blocks)
  // 只有一页时没有折叠的必要——折起来等于把唯一的内容藏起来。
  // 多页时默认展开有风险的页，其余收起以免一屏太长。
  const singlePage = pageNo === null && blocks.length > 0
  const [open, setOpen] = useState(singlePage || stats.flagged > 0)
  return (
    <div className="overflow-hidden rounded-[10px] border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 bg-secondary/50 px-3 py-1.5 text-left transition-colors hover:bg-secondary"
      >
        {open ? <ChevronDown className="h-3 w-3 flex-none" /> : <ChevronRight className="h-3 w-3 flex-none" />}
        <span className="text-[11px] font-semibold text-foreground">
          {pageNo === null ? '未标页码' : `第 ${pageNo} 页`}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {blocks.length} 块{stats.flagged > 0 ? ` · ${stats.flagged} 块待复核` : ''}
        </span>
      </button>
      {open && (
        <div>
          {blocks.map((b, i) => (
            <BlockRow key={`${pageNo}-${i}`} block={b} dimmed={!isBodyBlock(b)} />
          ))}
        </div>
      )}
    </div>
  )
}

const FILTERS: { value: ReviewFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'flagged', label: '待复核' },
  { value: 'scored', label: '已评估' },
  { value: 'unscored', label: '未评估' },
]

export function BlockReviewPanel({
  blocks,
  coverage,
}: {
  blocks: ParseBlock[] | null
  coverage: ParseCoverage | null
}) {
  const [filter, setFilter] = useState<ReviewFilter>('all')
  const [bodyOnly, setBodyOnly] = useState(true)

  const stats = useMemo(() => reviewStats(blocks ?? []), [blocks])

  const shown = useMemo(() => {
    const base = blocks ?? []
    const scoped = bodyOnly ? base.filter(isBodyBlock) : base
    return filterBlocks(scoped, filter)
  }, [blocks, bodyOnly, filter])

  const groups = useMemo(() => groupByPage(shown), [shown])

  // 后端明确说没有块结构（而不是"有但为空"）时给出能力说明，不渲染空面板
  if (!blocks || (blocks.length === 0 && !coverage?.has_blocks)) {
    return (
      <div className="flex items-start gap-2 rounded-[10px] border border-border bg-secondary/40 px-3 py-2.5">
        <ScanText className="mt-[1px] h-3.5 w-3.5 flex-none text-muted-foreground" />
        <div className="text-[11px] leading-relaxed text-muted-foreground">
          当前引擎未返回块级结构，无法做逐块复核。
          {coverage && !coverage.has_blocks && '（后端声明 has_blocks=false）'}
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-col gap-2">
      {/* 摘要行：如实说明有多少块未评估，不用「解析完成」替沉默背书 */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
        <span className="font-semibold text-foreground">{reviewHeadline(stats)}</span>
        {stats.risky > 0 && (
          <span className="text-status-red">
            <AlertTriangle className="mr-0.5 inline h-2.5 w-2.5" />
            {stats.risky} 块低分
          </span>
        )}
        {stats.unscored > 0 && <span className="text-muted-foreground">{stats.unscored} 块未评估</span>}
        {coverage && !canAttachConfidence(coverage) && (
          <span className="text-muted-foreground" title="后端声明缺少块坐标，无法从原图裁切局部送判定模型">
            · 本次无可裁切坐标
          </span>
        )}
      </div>

      {/* 工具行：筛选 + 只看正文 */}
      <div className="flex flex-wrap items-center gap-1">
        {FILTERS.map((f) => {
          const n =
            f.value === 'flagged'
              ? stats.flagged
              : f.value === 'scored'
                ? stats.total - stats.unscored
                : f.value === 'unscored'
                  ? stats.unscored
                  : stats.total
          return (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={cn(
                'rounded-[7px] px-2 py-[3px] text-[10.5px] font-medium transition-colors',
                filter === f.value
                  ? 'bg-foreground text-background'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
              )}
            >
              {f.label} {n}
            </button>
          )
        })}
        <button
          type="button"
          onClick={() => setBodyOnly((v) => !v)}
          className={cn(ROW_BTN, 'ml-auto', bodyOnly && 'border-foreground/30 bg-secondary')}
          title="页眉页脚页码常整段重复，默认隐藏"
        >
          只看正文
        </button>
      </div>

      {/* 块列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {groups.length === 0 ? (
          <div className="px-1 py-6 text-center text-[11px] text-muted-foreground">这个筛选下没有块</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {groups.map((g) => (
              <PageSection key={g.pageNo ?? 'none'} pageNo={g.pageNo} blocks={g.blocks} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
