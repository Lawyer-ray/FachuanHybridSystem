import type { ReactNode } from 'react'

import { SectionTitle, WorkCard } from './ui'

/**
 * 表格外框：白卡 + 贴边表头 + 贴边行。
 *
 * `court/`（四张）与 `oa/`（三张）两个兄弟子域共用，所以放在 `components/`
 * 而不是 `court/` 内部 —— 否则 `oa/*` 得深引兄弟子域的内部文件。
 *
 * 抽出来的唯一原因是口径一致 —— 七张表如果各自写 padding，
 * 行基线会歪一两像素，一屏之内就能看出来。
 */
export function PageTable({
  title,
  hint,
  action,
  head,
  children,
}: {
  title: string
  hint?: string
  action?: ReactNode
  /** `<th>` 列表，列宽写在这里 */
  head: ReactNode
  children: ReactNode
}) {
  return (
    <WorkCard padded={false}>
      <div className="border-b border-border-light px-5 py-3">
        <SectionTitle title={title} hint={hint} action={action} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border-light bg-secondary/30 text-[10.5px] text-muted-foreground [&>th]:px-5 [&>th]:py-2 [&>th]:font-medium">
              {head}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">{children}</tbody>
        </table>
      </div>
    </WorkCard>
  )
}
