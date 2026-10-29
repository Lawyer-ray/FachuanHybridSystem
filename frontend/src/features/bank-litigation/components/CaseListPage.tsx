import { useMemo, useState } from 'react'
import { AlertTriangle, ChevronRight, Gavel, RefreshCw } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'

import { useCases } from '../hooks/use-cases'
import { fmtMoney } from '../utils'
import type { CaseRow } from '../types'

/**
 * 银行批量诉讼 · 案件列表（场景 2 的入口）。
 *
 * ═══ 这一页要回答的问题 ═══
 * 律师手上有一批银行委托，每件都处在「签约 → 立项 → 准备 → 立案 → 归档」的
 * 不同位置。这一页把**当前阶段 + 就绪度**并排放在一行，让律师一眼看出
 * 「哪几件今天就能递、哪几件卡在缺材料」。
 *
 * ═══ 为什么不直接复用现有的案件列表 ═══
 * 现有列表服务的是「全部案件」的检索浏览；这一页服务的是「批量立案」的
 * 推进节奏，列不同、排序不同（按能否立案优先），是两种任务。
 */

/** 阶段 → 展示名与语气。与后端 CaseStage 枚举一一对应（含历史中文存量）。 */
const STAGE_LABEL: Record<string, string> = {
  first_trial: '一审',
  second_trial: '二审',
  enforcement: '执行',
  retrial_first: '重审一审',
  retrial_second: '重审二审',
  apply_retrial: '申请再审',
  rehearing_first: '再审一审',
  rehearing_second: '再审二审',
  review: '提审',
  labor_arbitration: '劳动仲裁',
  administrative_review: '行政复议',
  // 历史存量：早期数据存的是中文
  一审: '一审',
  二审: '二审',
  执行: '执行',
}

/** 案件状态 → 语气。在办中性、已结灰、可立案绿。 */
function statusTone(status: string): Tone {
  if (status === '已结案' || status === '已归档') return 'neutral'
  if (status === '在办') return 'blue'
  return 'neutral'
}

export function CaseListPage({ onOpen }: { onOpen: (caseId: number) => void }) {
  const { loading, error, data, reload } = useCases()
  const [keyword, setKeyword] = useState('')

  const rows = useMemo<CaseRow[]>(() => {
    const list = (data ?? []) as unknown as CaseRow[]
    const kw = keyword.trim()
    const filtered = kw
      ? list.filter(
          (c) => c.name.includes(kw) || (c.cause_of_action ?? '').includes(kw),
        )
      : list
    // 排序：待立案（无案号、在办）优先，其次按 id 倒序（新的在上）
    return [...filtered].sort((a, b) => {
      const aF = !a.filing_number && a.status === '在办' ? 0 : 1
      const bF = !b.filing_number && b.status === '在办' ? 0 : 1
      if (aF !== bF) return aF - bF
      return b.id - a.id
    })
  }, [data, keyword])

  if (loading) return <LoadingBlock text="正在加载案件…" />
  if (error) {
    return <ErrorBlock error={error} fallback="案件列表加载失败" onRetry={reload} />
  }
  if (!rows.length) {
    return <EmptyBlock icon={<Gavel className="size-6" />}>还没有案件，先受理一笔委托。</EmptyBlock>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜案件名 / 案由"
          className="h-[30px] w-[240px] rounded-[7px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/60"
        />
        <span className="text-[11.5px] text-muted-foreground">
          共 {rows.length} 件
        </span>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={reload}>
          <RefreshCw className="size-3.5" /> 刷新
        </Button>
      </div>

      <div className="overflow-hidden rounded-[10px] border border-border bg-card">
        <div className="grid grid-cols-[1fr_72px_96px_120px_132px_28px] items-center gap-3 border-b border-border bg-secondary/40 px-4 py-2 text-[11px] font-medium text-muted-foreground">
          <span>案件</span>
          <span>阶段</span>
          <span>状态</span>
          <span>案号</span>
          <span>标的额</span>
          <span />
        </div>
        {rows.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => onOpen(c.id)}
            className="grid w-full grid-cols-[1fr_72px_96px_120px_132px_28px] items-center gap-3 border-b border-border/60 px-4 py-2.5 text-left transition-colors last:border-b-0 hover:bg-secondary/40"
          >
            <div className="min-w-0">
              <div className="truncate text-[13px] text-foreground" title={c.name}>
                {c.name}
              </div>
              <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
                {c.cause_of_action || '（未填案由）'}
                {c.contract_name ? ` · ${c.contract_name}` : ''}
              </div>
            </div>
            <span className="text-[12px] text-secondary-foreground">
              {STAGE_LABEL[c.current_stage ?? ''] ?? c.current_stage ?? '—'}
            </span>
            <StatusBadge tone={statusTone(c.status)}>{c.status || '—'}</StatusBadge>
            <span className="truncate text-[11.5px] text-muted-foreground" title={c.filing_number || ''}>
              {c.filing_number || '（无）'}
            </span>
            <span className="text-right text-[12px] tabular-nums text-secondary-foreground">
              {c.target_amount ? `¥${fmtMoney(c.target_amount)}` : '—'}
            </span>
            <ChevronRight className="size-3.5 text-muted-foreground" />
          </button>
        ))}
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <AlertTriangle className="size-3" />
        标的额取自案件登记值；实际诉请金额以利息计算表为准（两处不一致时以计算表为准）。
      </p>
    </div>
  )
}
