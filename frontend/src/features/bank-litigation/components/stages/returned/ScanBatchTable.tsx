/**
 * 回扫 —— 行政扫描批次。
 *
 * 扫描仪每次扫完自动转发到邮箱，这里按批次列出来：多少页、匹配到哪个案、
 * 匹配度（低于 80% 用警示色）、自动归案还是待人工。
 * 纯展示，数据全来自演示常量。
 */
import { DEMO_SCAN_BATCHES } from '../../demo-data'
import { Pill, SectionTitle, WorkCard } from '../../ui'

/** 行政扫描批次表 */
export function ScanBatchTable() {
  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle title="行政扫描批次" hint="扫描仪自动转发到邮箱" className="w-full" />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_SCAN_BATCHES.map((b) => (
          <li key={b.batch} className="flex items-center gap-3 px-5 py-2.5">
            <span className="min-w-0 flex-1 truncate text-[12px]" title={b.batch}>{b.batch}</span>
            <span className="w-[54px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">{b.pages} 页</span>
            <span className="w-[150px] flex-none truncate text-[10.5px] text-muted-foreground" title={b.matched}>{b.matched}</span>
            <span className="w-[44px] flex-none text-right text-[10.5px] tabular-nums"
              style={{color: b.confidence >= 0.8 ? undefined : 'var(--status-yellow)'}}>
              {(b.confidence * 100).toFixed(0)}%
            </span>
            <Pill tone={b.status === 'auto' ? 'green' : 'yellow'}>{b.status === 'auto' ? '自动归案' : '待人工'}</Pill>
            <span className="w-[82px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">{b.scannedAt}</span>
          </li>
        ))}
      </ul>
    </WorkCard>
  )
}
