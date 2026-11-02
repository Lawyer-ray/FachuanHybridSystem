import { PageTable } from './PageTable'
import { Pill } from '../ui'

import { DEMO_COURT_SUBMIT_HISTORY, type CourtSubmitHistoryRow } from '../demo-data'

const RESULT_META: Record<CourtSubmitHistoryRow['result'], { text: string; tone: 'green' | 'red' | 'yellow' | 'neutral' }> = {
  accepted: { text: '已受理', tone: 'green' },
  returned: { text: '法院退回', tone: 'red' },
  failed: { text: '递交失败', tone: 'yellow' },
  pending: { text: '待处理', tone: 'neutral' },
}

/**
 * 历史递交记录（时间倒序）。
 *
 * 批量诉讼里同一件案子会被递交多次 —— 退回、补正、换法院重交都会留一条。
 * 律师真正想知道的是「上一次为什么没过」，所以退回与失败必须能一眼数出来。
 */
export function SubmitHistory() {
  const rows = DEMO_COURT_SUBMIT_HISTORY
  const accepted = rows.filter((r) => r.result === 'accepted').length
  const returned = rows.filter((r) => r.result === 'returned').length

  return (
    <PageTable
      title="历史递交记录"
      hint={`共 ${rows.length} 次 · 已受理 ${accepted} · 退回 ${returned}`}
      head={
        <>
          <th className="w-[118px]">时间</th>
          <th className="w-[152px]">批次号</th>
          <th>案号</th>
          <th className="w-[92px]">结果</th>
          <th className="w-[150px]">受理号</th>
        </>
      }
    >
      {rows.map((r) => {
        const meta = RESULT_META[r.result]
        return (
          <tr key={r.id}>
            <td className="py-2 pl-5 pr-3 text-[11.5px] tabular-nums text-muted-foreground">{r.at}</td>
            <td className="py-2 pr-3 text-[11.5px] tabular-nums">{r.batch}</td>
            <td className="py-2 pr-3">
              <div className="truncate text-[11.5px]" title={r.filingNumber}>
                {r.filingNumber}
              </div>
            </td>
            <td className="py-2 pr-3">
              <Pill tone={meta.tone}>{meta.text}</Pill>
            </td>
            <td className="py-2 pr-5 text-[11.5px] tabular-nums text-muted-foreground">
              {r.receipt}
            </td>
          </tr>
        )
      })}
    </PageTable>
  )
}
