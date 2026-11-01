import { PageTable } from './PageTable'
import { Pill } from '../ui'

import { DEMO_COURT_FIELD_MAPPING } from '../demo-data'

/**
 * 字段映射表：法穿字段 → 一张网表单字段。
 *
 * 这张表回答的是「机器到底替我填了什么」——律师敢不敢点提交，
 * 取决于他能不能一眼看出哪个格子是机器猜的。所以状态只有两种：
 * 已映射（机器有把握）/ 待确认（机器拿不准，附一句为什么）。
 */
export function FieldMappingTable() {
  const rows = DEMO_COURT_FIELD_MAPPING
  const mapped = rows.filter((r) => r.status === 'mapped').length
  const pending = rows.length - mapped

  return (
    <PageTable
      title="字段映射"
      hint={`法穿字段 → 一张网表单字段 · ${mapped}/${rows.length} 已映射`}
      action={
        pending > 0 ? (
          <Pill tone="yellow">{pending} 项待确认</Pill>
        ) : (
          <Pill tone="green">全部已映射</Pill>
        )
      }
      head={
        <>
          <th className="w-[168px]">法穿字段</th>
          <th className="w-[136px]">一张网表单字段</th>
          <th>填报值</th>
          <th className="w-[76px] text-right">状态</th>
        </>
      }
    >
      {rows.map((r) => (
        <tr key={r.from} className="align-top">
          <td className="py-2 pl-5 pr-3 text-[11.5px] text-muted-foreground">{r.from}</td>
          <td className="py-2 pr-3 text-[11.5px] font-medium">{r.to}</td>
          <td className="py-2 pr-3">
            <div className="truncate text-[11.5px] tabular-nums" title={r.value}>
              {r.value}
            </div>
            {r.note ? (
              <div className="mt-0.5 text-[10.5px] leading-[1.5] text-status-yellow">{r.note}</div>
            ) : null}
          </td>
          <td className="py-2 pr-5 text-right">
            <Pill tone={r.status === 'mapped' ? 'green' : 'yellow'}>
              {r.status === 'mapped' ? '已映射' : '待确认'}
            </Pill>
          </td>
        </tr>
      ))}
    </PageTable>
  )
}
