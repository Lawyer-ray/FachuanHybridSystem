import { FileText } from 'lucide-react'

import { PageTable } from './PageTable'
import { Pill } from '../ui'

import { DEMO_COURT_MATERIALS, type CourtMaterialRow } from '../demo-data'

const STAMP_META: Record<CourtMaterialRow['stamp'], { text: string; tone: 'green' | 'yellow' | 'red' }> = {
  stamped: { text: '已盖章', tone: 'green' },
  partial: { text: '部分盖章', tone: 'yellow' },
  none: { text: '未盖章', tone: 'red' },
}

/**
 * 随案材料清单。
 *
 * 封面盖章与上传是两件独立的事 —— 盖了章没上传照样递交不了。
 * 所以三列分开写（页数 / 盖章 / 上传时间），别合并成一个「状态」。
 */
export function MaterialList() {
  const rows = DEMO_COURT_MATERIALS
  const uploaded = rows.filter((r) => r.uploadedAt).length
  const pages = rows.reduce((s, r) => s + r.pages, 0)

  return (
    <PageTable
      title="随案材料"
      hint={`共 ${rows.length} 份 · ${pages} 页 · 已上传 ${uploaded}/${rows.length}`}
      head={
        <>
          <th>材料名称</th>
          <th className="w-[64px] text-right">页数</th>
          <th className="w-[92px]">盖章状态</th>
          <th className="w-[104px] text-right">上传时间</th>
        </>
      }
    >
      {rows.map((r) => {
        const stamp = STAMP_META[r.stamp]
        return (
          <tr key={r.id}>
            <td className="py-2 pl-5 pr-3">
              <div className="flex items-center gap-1.5">
                <FileText className="size-3 flex-none text-muted-foreground" />
                <span className="truncate text-[11.5px]" title={r.name}>
                  {r.name}
                </span>
              </div>
            </td>
            <td className="py-2 pr-3 text-right text-[11.5px] tabular-nums text-muted-foreground">
              {r.pages}
            </td>
            <td className="py-2 pr-3">
              <Pill tone={stamp.tone}>{stamp.text}</Pill>
            </td>
            <td className="py-2 pr-5 text-right text-[11.5px] tabular-nums text-muted-foreground">
              {r.uploadedAt ?? '未上传'}
            </td>
          </tr>
        )
      })}
    </PageTable>
  )
}
