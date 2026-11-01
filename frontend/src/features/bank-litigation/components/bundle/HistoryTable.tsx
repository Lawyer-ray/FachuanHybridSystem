import { FileStack } from 'lucide-react'

import { cn } from '@/lib/utils'

import { DEMO_BUNDLE_SPLIT_RECORDS } from '../demo-data'
import { Pill, SectionTitle, WorkCard } from '../ui'

const RESULT_META = {
  confirmed: { tone: 'green', text: '已确认' },
  review: { tone: 'yellow', text: '需复核' },
  unrecognized: { tone: 'red', text: '未识别' },
} as const

const COLUMNS = 'grid-cols-[minmax(0,1fr)_86px_92px_74px_64px_58px_82px_74px_64px]'

/**
 * 拆分记录表：45 天内的每一次整包拆分。
 *
 * 为什么要在 idle 态摆一张长表：律师重新打开案件时最想知道的是
 * 「这包我之前拆过没有、拆成什么样」，而不是再看一遍上传指引。
 * 列为「包 → 案由 → 页/份 → 方式 → 结果 → 需复核 → 归案 → 耗时 → 时间 → 操作人」。
 */
export function HistoryTable() {
  const totalPages = DEMO_BUNDLE_SPLIT_RECORDS.reduce((s, r) => s + r.pages, 0)
  const totalMaterials = DEMO_BUNDLE_SPLIT_RECORDS.reduce((s, r) => s + r.materials, 0)

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="拆分记录"
          hint={`最近 ${DEMO_BUNDLE_SPLIT_RECORDS.length} 包 · 合计 ${totalPages.toLocaleString('zh-CN')} 页 / ${totalMaterials} 份`}
          className="w-full"
        />
      </div>

      <div
        className={cn(
          'grid gap-2 border-b border-border-light bg-secondary/40 px-5 py-1.5 text-[10.5px] font-medium text-muted-foreground',
          COLUMNS,
        )}
      >
        <span>整包文件</span>
        <span>案由</span>
        <span className="text-right">页 / 份</span>
        <span>方式</span>
        <span>结果</span>
        <span className="text-right">需复核</span>
        <span className="text-right">归案</span>
        <span className="text-right">耗时</span>
        <span className="text-right">时间</span>
      </div>

      <ul className="divide-y divide-border-light">
        {DEMO_BUNDLE_SPLIT_RECORDS.map((r) => {
          const meta = RESULT_META[r.result]
          return (
            <li key={r.id} className={cn('grid items-center gap-2 px-5 py-2', COLUMNS)}>
              <div className="flex min-w-0 items-center gap-2">
                <FileStack className="size-3.5 flex-none text-muted-foreground" />
                <span className="min-w-0 truncate text-[12px]" title={r.fileName}>
                  {r.fileName}
                </span>
              </div>
              <span className="truncate text-[11px] text-muted-foreground" title={r.causeOfAction}>
                {r.causeOfAction.replace('合同纠纷', '').replace('纠纷', '')}
              </span>
              <span className="text-right text-[11px] tabular-nums text-muted-foreground">
                {r.pages} / {r.materials}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {r.mode === 'content' ? '内容识别' : '分隔页'}
              </span>
              <span>
                <Pill tone={meta.tone}>{meta.text}</Pill>
              </span>
              <span
                className={cn(
                  'text-right text-[11px] tabular-nums',
                  r.flagged > 0 ? 'text-status-yellow' : 'text-muted-foreground',
                )}
              >
                {r.flagged > 0 ? `${r.flagged} 段` : '—'}
              </span>
              <span className="text-right text-[11px] tabular-nums text-muted-foreground">
                {r.imported ? `${r.imported} 份` : '未归案'}
              </span>
              <span className="text-right text-[11px] tabular-nums text-muted-foreground">
                {r.elapsed}
              </span>
              <span className="text-right text-[10.5px] tabular-nums text-muted-foreground" title={r.by}>
                {r.at}
              </span>
            </li>
          )
        })}
      </ul>
    </WorkCard>
  )
}
