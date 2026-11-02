import { DEMO_READINESS_FILES } from '../demo-data'
import { ActionButton, SectionTitle, WorkCard } from '../ui'

const COLUMNS = 'grid-cols-[minmax(0,1fr)_150px_62px_78px_96px_88px]'

/**
 * 材料清单明细：本案已归案的每一个文件（文件名 / 槽位 / 页数 / 大小 / 时间 / 来源）。
 *
 * 为什么要有这张表：上面的「材料齐备」只回答缺不缺；齐备的具体是哪几个文件、
 * 多大、什么时候传的，递交前要逐份核对 —— 这张表就是那份可核对清单。
 */
export function MaterialFileList() {
  const totalPages = DEMO_READINESS_FILES.reduce((s, f) => s + f.pages, 0)

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="材料清单明细"
          hint={`共 ${DEMO_READINESS_FILES.length} 个文件 · ${totalPages} 页`}
          className="w-full"
          action={<ActionButton sm>导出清单</ActionButton>}
        />
      </div>
      <div
        className={`grid ${COLUMNS} gap-2 border-b border-border-light bg-secondary/40 px-5 py-1.5 text-[10.5px] font-medium text-muted-foreground`}
      >
        <span>文件名</span>
        <span>所属槽位</span>
        <span className="text-right">页数</span>
        <span className="text-right">大小</span>
        <span>上传时间</span>
        <span>来源</span>
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_READINESS_FILES.map((f) => (
          <li key={f.name} className={`grid ${COLUMNS} items-center gap-2 px-5 py-2`}>
            <span className="min-w-0 truncate text-[12px]" title={f.name}>
              {f.name}
            </span>
            <span className="truncate text-[11px] text-muted-foreground" title={f.slot}>
              {f.slot}
            </span>
            <span className="text-right text-[11px] tabular-nums text-muted-foreground">{f.pages}</span>
            <span className="text-right text-[11px] tabular-nums text-muted-foreground">{f.size}</span>
            <span className="text-[10.5px] tabular-nums text-muted-foreground">{f.at}</span>
            <span className="text-[10.5px] text-muted-foreground">{f.source}</span>
          </li>
        ))}
      </ul>
    </WorkCard>
  )
}
