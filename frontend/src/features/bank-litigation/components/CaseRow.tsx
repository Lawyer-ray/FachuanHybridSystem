import { ChevronRight } from 'lucide-react'

import { StatusBadge } from '@/components/shared/StatusBadge'
import type { Tone } from '@/lib/tone'

import { fmtMoney } from '../utils'
// 组件名 CaseRow 与 types.ts 的行类型同名，类型这边加 Data 后缀区分
import type { CaseRow as CaseRowData } from '../types'

/**
 * 行 / 表头共用的列宽定义（案件 / 阶段 / 状态 / 案号 / 标的额 / 箭头）。
 *
 * 抽出来是为了让表头、真行、骨架行（`CaseRowSkeleton`）用**同一串**列宽：
 * 任何一处单独改，列基线就歪一两像素，一屏之内就能看出来。
 */
export const CASE_ROW_COLUMNS = 'grid-cols-[1fr_72px_96px_120px_132px_28px]'

/**
 * 行容器结构类：列宽 / 间距 / 边框 / 分隔线。
 *
 * 抽成常量是为了让骨架行复用**同一串**类（与 workbench 的 `DEAL_ROW_SHELL`
 * 同做法）。骨架与真行只要差 1px 内边距，数据到位时整页就会跳一下。
 * 只放结构类：`transition-colors` / `hover:bg-secondary/40`（交互）留在 CaseRow 身上，
 * 骨架不需要它们。
 */
export const CASE_ROW_SHELL = `grid w-full ${CASE_ROW_COLUMNS} items-center gap-3 border-b border-border/60 px-4 py-2.5 text-left last:border-b-0`

/**
 * 列表表头。与真行 / 骨架行共用 `CASE_ROW_COLUMNS`，所以三者列基线永远对齐。
 *
 * 为什么抽成组件而不是写在页面里：骨架（`CaseRowSkeleton`）也要画**同一份**表头。
 * 不画的话，首屏骨架少了这 ~29px，数据到位时整块列表向下位移；各写一份的话，
 * 将来改列名 / 改列宽又会出现"表头与骨架各改各的"。这里是唯一来源。
 */
export function CaseListHeader() {
  return (
    <div
      className={`grid ${CASE_ROW_COLUMNS} items-center gap-3 border-b border-border bg-secondary/40 px-4 py-2 text-[11px] font-medium text-muted-foreground`}
    >
      <span>案件</span>
      <span>阶段</span>
      <span>状态</span>
      <span>案号</span>
      <span>标的额</span>
      <span />
    </div>
  )
}

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

/** 列表行：案件名 + 案由 / 阶段 / 状态 / 案号 / 标的额，整行可点进案件详情。 */
export function CaseRow({ c, onOpen }: { c: CaseRowData; onOpen: (caseId: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => {
        // id 可空：这种脏行点不开，早退而不是把 0 当案件 id 传给上层
        if (c.id == null) return
        onOpen(c.id)
      }}
      className={`${CASE_ROW_SHELL} transition-colors hover:bg-secondary/40`}
    >
      <div className="min-w-0">
        <div className="truncate text-[13px] text-foreground" title={c.name}>
          {c.name}
        </div>
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {c.cause_of_action || '（未填案由）'}
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
  )
}
