/**
 * OA 盖章面板的 5 张只读表（批量预设 / 印章库 / 位置规则 / 盖章记录 / 失败原因）。
 *
 * 全是**展示**，不参与任何判断：数据来自 demo-data，点了也不改变什么。
 * 从 `OAActionPanels.tsx` 抽出来的原因只有一个 —— 那 5 段原来由 5 个独立的
 * `kind === 'stamp' ? … : null` 三元块控制，把面板的编排（输入 → 反查 → 提交 → 会话）
 * 埋在了 300 多行展示代码中间。拆出来后面板只剩编排。
 */

import { Pill, SectionTitle, WorkCard } from '../ui'
import {
  DEMO_OA_SEAL_RULES,
  DEMO_OA_SEALS,
  DEMO_STAMP_BATCHES,
  DEMO_STAMP_FAILURES,
  DEMO_STAMP_HISTORY,
} from '../demo-data'

/** 表头：白卡 + 贴边标题栏（这几张表都是 `padded={false}` + 标题栏 + 分隔线列表） */
function TableCard({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle title={title} hint={hint} className="w-full" />
      </div>
      {children}
    </WorkCard>
  )
}

/** 批量盖章预设：一次盖齐一整套材料 */
export function StampBatchPresets() {
  return (
    <TableCard title="批量盖章预设" hint="一次盖齐一整套材料">
      <ul className="divide-y divide-border-light">
        {DEMO_STAMP_BATCHES.map((b) => (
          <li key={b.name} className="flex items-start gap-3 px-5 py-2.5">
            <span className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-[12px] font-medium">{b.name}</span>
                <Pill tone="blue">{b.seals}</Pill>
                <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
                  {b.docs} 份 · {b.pages} 页
                </span>
              </div>
              <div className="mt-0.5 text-[10.5px] text-muted-foreground">{b.note}</div>
            </span>
          </li>
        ))}
      </ul>
    </TableCard>
  )
}

/** 印章库：有哪些章、谁保管、这个月用了几次 */
export function StampSealLibrary() {
  return (
    <TableCard title="可用印章" hint={`${DEMO_OA_SEALS.filter((x) => x.status === 'available').length} 枚可用`}>
      <ul className="divide-y divide-border-light">
        {DEMO_OA_SEALS.map((x) => (
          <li key={x.name} className="flex items-center gap-3 px-5 py-2.5">
            <span className="min-w-0 flex-1 truncate text-[12px]" title={x.name}>{x.name}</span>
            <Pill>{x.kind}</Pill>
            <span className="w-[60px] flex-none text-[11px] text-muted-foreground">{x.holder}</span>
            <Pill tone={x.status === 'available' ? 'green' : x.status === 'in-use' ? 'yellow' : 'red'}>
              {x.status === 'available' ? '可用' : x.status === 'in-use' ? '使用中' : '已停用'}
            </Pill>
            <span className="w-[52px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">
              {x.usedThisMonth} 次
            </span>
            <span className="w-[82px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
              {x.lastUsed}
            </span>
          </li>
        ))}
      </ul>
    </TableCard>
  )
}

/** 盖章位置规则：哪类文书盖哪些章、盖在哪 */
export function StampSealRules() {
  return (
    <TableCard title="盖章位置规则" hint="哪类文书盖哪些章、盖在哪">
      <ul className="divide-y divide-border-light">
        {DEMO_OA_SEAL_RULES.map((r) => (
          <li key={r.docType} className="px-5 py-2.5">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-medium">{r.docType}</span>
              <Pill tone="blue">{r.seals}</Pill>
              <span className="ml-auto text-[11px] text-muted-foreground">{r.position}</span>
            </div>
            <div className="mt-0.5 text-[10.5px] text-muted-foreground">{r.note}</div>
          </li>
        ))}
      </ul>
    </TableCard>
  )
}

/** 盖章记录：最近若干次，失败直接给后端原话 */
export function StampHistoryTable() {
  return (
    <TableCard title="盖章记录" hint={`最近 ${DEMO_STAMP_HISTORY.length} 次`}>
      <ul className="divide-y divide-border-light">
        {DEMO_STAMP_HISTORY.map((r) => (
          <li key={r.fileName + r.at} className="flex items-center gap-3 px-5 py-2.5">
            <span
              className={
                r.ok
                  ? 'grid size-4 flex-none place-items-center rounded-full bg-status-green'
                  : 'grid size-4 flex-none place-items-center rounded-full bg-status-red'
              }
            >
              <span className="text-[9px] font-bold text-white">{r.ok ? '✓' : '✕'}</span>
            </span>
            <span className="min-w-0 flex-1 truncate text-[12px]" title={r.fileName}>{r.fileName}</span>
            <Pill>{r.page}</Pill>
            {r.ok ? (
              <Pill tone="green">已盖章</Pill>
            ) : (
              <span className="max-w-[180px] truncate text-[10.5px] text-status-red" title={r.reason}>
                {r.reason}
              </span>
            )}
            <span className="w-[64px] flex-none text-right text-[10.5px] text-muted-foreground">{r.by}</span>
            <span className="w-[82px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">{r.at}</span>
          </li>
        ))}
      </ul>
    </TableCard>
  )
}

/** 常见失败原因：近 30 天，能自动重试的与要人处理的分别标出来 */
export function StampFailureCauses() {
  return (
    <TableCard title="常见失败原因" hint="近 30 天">
      <ul className="divide-y divide-border-light">
        {DEMO_STAMP_FAILURES.map((f) => (
          <li key={f.cause} className="px-5 py-2.5">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-medium">{f.cause}</span>
              <Pill>{f.stage}</Pill>
              <Pill tone={f.autoRetry ? 'green' : 'yellow'}>{f.autoRetry ? '自动重试' : '需人工'}</Pill>
              <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">{f.last30} 次</span>
            </div>
            <div className="mt-0.5 text-[10.5px] text-muted-foreground">{f.advice}</div>
          </li>
        ))}
      </ul>
    </TableCard>
  )
}
