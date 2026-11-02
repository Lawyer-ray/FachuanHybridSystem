/**
 * OA 立案 · 历史立案记录表。
 *
 * ═══ 这张表解决什么问题 ═══
 * 「在 OA 立案」这个按钮点下去要跑几十秒，律师在等的时候需要一份**可信的旁证**：
 * 上一次立的是哪件案子、多久、成没成。所以表里固定给三样东西 ——
 * 时间戳（精确到分钟）、耗时（真实量级，不是「几秒」）、状态（已立案/审批中/已退回）。
 *
 * 数据是演示态（`DEMO_OA_HISTORY`）：真实实现应来自 oa-filing 会话表，
 * 面板只做只读呈现，不参与任何判断。外框与一张网那几张表共用 `court/PageTable`，
 * 保证同一工作台里所有表格的行基线一致。
 */

import { PageTable } from '../court/PageTable'
import { Pill } from '../ui'
import { DEMO_OA_HISTORY, type OAFilingHistoryRow } from '../demo-data'

const STATE_LABEL: Record<OAFilingHistoryRow['state'], string> = {
  filed: '已立案',
  pending: '审批中',
  returned: '已退回',
}

const STATE_TONE: Record<OAFilingHistoryRow['state'], 'green' | 'yellow' | 'red'> = {
  filed: 'green',
  pending: 'yellow',
  returned: 'red',
}

export function OAHistoryTable() {
  const filed = DEMO_OA_HISTORY.filter((r) => r.state === 'filed').length
  const returned = DEMO_OA_HISTORY.filter((r) => r.state === 'returned').length

  return (
    <PageTable
      title="历史立案记录"
      hint={`近 ${DEMO_OA_HISTORY.length} 次 · 已立案 ${filed} · 退回 ${returned}`}
      head={
        <>
          <th className="w-[132px]">所内案号</th>
          <th>委托人</th>
          <th className="w-[124px] text-right">标的额</th>
          <th className="w-[124px] text-right">OA 案号</th>
          <th className="w-[82px]">状态</th>
          <th className="w-[80px] text-right">耗时</th>
          <th className="w-[92px] text-right">时间</th>
        </>
      }
    >
      {DEMO_OA_HISTORY.map((r) => (
        <tr key={`${r.oaCaseNo}-${r.at}`}>
          <td className="py-2 pl-5 pr-3 text-[11.5px] tabular-nums">{r.caseNo}</td>
          <td className="max-w-0 truncate py-2 pr-3 text-[12px]" title={r.client}>
            {r.client}
          </td>
          <td className="py-2 pr-3 text-right text-[11.5px] font-medium tabular-nums">{r.amount}</td>
          <td className="py-2 pr-3 text-right text-[11px] tabular-nums text-muted-foreground">{r.oaCaseNo}</td>
          <td className="py-2 pr-3">
            <Pill tone={STATE_TONE[r.state]}>{STATE_LABEL[r.state]}</Pill>
          </td>
          <td className="py-2 pr-3 text-right text-[10.5px] tabular-nums text-muted-foreground">{r.cost}</td>
          <td className="py-2 pr-5 text-right text-[10.5px] tabular-nums text-muted-foreground">{r.at}</td>
        </tr>
      ))}
    </PageTable>
  )
}
