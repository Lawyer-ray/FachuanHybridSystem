import { AlertTriangle } from 'lucide-react'

import { PageTable } from './PageTable'
import { Pill } from '../ui'

import { DEMO_COURT_AMOUNT_CHECK } from '../demo-data'

/**
 * 三处金额校验：起诉状 / 一张网表单 / 要素式字段。
 *
 * 立案被退回最常见的原因就是标的额对不上，而手工改一处的概率极高。
 * 所以不写一句「金额不一致」，而是三列并排把数摆出来 ——
 * 律师能直接看出是哪个数被动了、差多少。
 */
export function AmountCheckTable() {
  const rows = DEMO_COURT_AMOUNT_CHECK
  const failed = rows.filter((r) => !r.ok)

  return (
    <PageTable
      title="三处金额校验"
      hint={`起诉状 · 一张网表单 · 要素式字段 · ${rows.length - failed.length}/${rows.length} 一致`}
      action={
        failed.length ? (
          <Pill tone="red">{failed.length} 项不一致</Pill>
        ) : (
          <Pill tone="green">全部一致</Pill>
        )
      }
      head={
        <>
          <th className="w-[132px]">项目</th>
          <th className="w-[122px] text-right">起诉状标的</th>
          <th className="w-[122px] text-right">一张网标的</th>
          <th className="w-[122px] text-right">要素式标的</th>
          <th>差异说明</th>
        </>
      }
    >
      {rows.map((r) => (
        <tr key={r.item} className={r.ok ? '' : 'bg-status-red-bg/40'}>
          <td className="py-2 pl-5 pr-3 text-[11.5px] font-medium">{r.item}</td>
          <td className="py-2 pr-3 text-right text-[11.5px] tabular-nums">{r.fromPleading}</td>
          <td
            className={
              'py-2 pr-3 text-right text-[11.5px] tabular-nums' +
              (r.ok ? '' : ' font-semibold text-status-red')
            }
          >
            {r.fromCourtForm}
          </td>
          <td className="py-2 pr-3 text-right text-[11.5px] tabular-nums">{r.fromElement}</td>
          <td className="py-2 pr-5 text-[11px] leading-[1.5]">
            {r.ok ? (
              <span className="text-muted-foreground">一致</span>
            ) : (
              <span className="inline-flex items-start gap-1 text-status-red">
                <AlertTriangle className="mt-[2px] size-3 flex-none" />
                {r.diff}
              </span>
            )}
          </td>
        </tr>
      ))}
    </PageTable>
  )
}
