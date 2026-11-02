/**
 * OA 立案 · 字段映射表（法穿字段 → OA 收案登记字段）。
 *
 * ═══ 为什么要把映射摊开给人看 ═══
 * 「机器自动填表」最让人不放心的就是填错了地方 —— 标的额填进代理费、
 * 委托人填成对方当事人。这张表就是那句「你不用信我，自己核对」：
 * 左边是法穿里的字段名（律师认识），右边是 OA 里的表单字段名（OA 认识）。
 *
 * 取值来源一列是重点：`案件数据` / `委托合同` 是确定的，`系统推断` 可能猜错
 * （比如委托人类型），`手工补录` 则必须有人动手。故来源列保留颜色 ——
 * 律师扫一眼就知道哪几行需要自己核对。演示态常量 `DEMO_OA_FIELD_MAPPING`。
 */

import { PageTable } from '../court/PageTable'
import { Pill } from '../ui'
import { DEMO_OA_FIELD_MAPPING, type OAFieldMappingRow } from '../demo-data'

const SOURCE_LABEL: Record<OAFieldMappingRow['source'], string> = {
  case: '案件数据',
  contract: '委托合同',
  infer: '系统推断',
  manual: '手工补录',
}

const SOURCE_TONE: Record<OAFieldMappingRow['source'], 'neutral' | 'green' | 'yellow' | 'blue'> = {
  case: 'green',
  contract: 'green',
  infer: 'yellow',
  manual: 'blue',
}

export function OAFieldMapping() {
  const needCheck = DEMO_OA_FIELD_MAPPING.filter((m) => m.source === 'infer' || m.source === 'manual').length

  return (
    <PageTable
      title="字段映射"
      hint={`法穿 → OA 收案登记 · ${DEMO_OA_FIELD_MAPPING.length} 项`}
      action={<Pill tone={needCheck ? 'yellow' : 'green'}>{needCheck} 项需人工核对</Pill>}
      head={
        <>
          <th className="w-[132px]">法穿字段</th>
          <th>OA 表单字段</th>
          <th className="w-[92px] text-right">取值来源</th>
        </>
      }
    >
      {DEMO_OA_FIELD_MAPPING.map((m) => (
        <tr key={m.from}>
          <td className="py-2 pl-5 pr-3 text-[11.5px] text-muted-foreground">{m.from}</td>
          <td className="max-w-0 truncate py-2 pr-3 text-[12px]" title={m.to}>
            {m.to}
          </td>
          <td className="py-2 pr-5 text-right">
            {/* 推断/补录不是机器能确定的，这两类要人核 */}
            <Pill tone={SOURCE_TONE[m.source]}>{SOURCE_LABEL[m.source]}</Pill>
          </td>
        </tr>
      ))}
    </PageTable>
  )
}
