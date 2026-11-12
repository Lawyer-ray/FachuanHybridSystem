/**
 * ③ 缺件 —— 来源分组切换条（全部 / 合同类 / 催收类 / 身份类 / 担保类）。
 *
 * 每个分组后面跟当前条数，切分组只影响下面的缺件清单，不改任何数据。
 */
import type { GapSource } from '../../demo-data'
import { cn } from '@/lib/utils'

import { SOURCE_TABS, countBySource } from './gap-utils'

/** 来源分组切换条 */
export function GapSourceTabs({
  value,
  onChange,
}: {
  value: '全部' | GapSource
  onChange: (tab: '全部' | GapSource) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-border-light px-5 py-2.5">
      <span className="text-[10.5px] text-muted-foreground">按来源</span>
      {SOURCE_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          aria-pressed={value === tab}
          onClick={() => onChange(tab)}
          className={cn(
            'h-[24px] rounded-[6px] border px-2 text-[11px] transition-colors',
            value === tab
              ? 'border-foreground bg-foreground font-semibold text-background'
              : 'border-border bg-card font-[550] text-secondary-foreground hover:bg-secondary',
          )}
        >
          {tab}
          <span className={cn('ml-1 tabular-nums', value === tab ? 'opacity-70' : 'text-muted-foreground')}>
            {countBySource(tab)}
          </span>
        </button>
      ))}
    </div>
  )
}
