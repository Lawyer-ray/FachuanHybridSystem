/**
 * 整包里的源文件清单：每行带下载 / 剔除
 *
 * 为什么需要行内按钮：客户发来的包里常混着「不该进后续阶段」的文件
 * （别的案件的扫描页、银行内部批注、重复件）。以前只能整包收下，
 * 剔除要么重新上传、要么到后面阶段逐个排除。这里让它在**源文件这一层**就处理掉，
 * 剔掉的文件不再计入页数，也不进「读懂」。
 */

import { Download, MinusCircle } from 'lucide-react'

import { DEMO_INTAKE_SOURCES } from '../demo-data'
import { ActionButton, Pill, SectionTitle, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

export function IntakeSourceCard({
  dropped,
  onToggle,
  pages,
}: {
  /** 已剔除的源文件名 */
  dropped: Set<string>
  onToggle: (name: string) => void
  /** 剩余源文件的总页数（剔除后实时变化） */
  pages: number
}) {
  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="整包里的源文件"
          hint={`${DEMO_INTAKE_SOURCES.length - dropped.size} 个源文件合并成 ${pages} 页`}
          className="w-full"
        />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_INTAKE_SOURCES.map((f) => {
          const isDropped = dropped.has(f.name)
          return (
            <li key={f.name} className={cn('flex items-center gap-3 px-5 py-2', isDropped && 'bg-secondary/30')}>
              <span
                className={cn('min-w-0 flex-1 truncate text-[12px]', isDropped && 'text-muted-foreground line-through')}
                title={f.name}
              >
                {f.name}
              </span>
              <Pill>{f.kind}</Pill>
              <span className="w-[52px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">
                {f.pages} 页
              </span>
              <span className="w-[60px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                {f.size}
              </span>
              <span className="flex w-[92px] flex-none items-center justify-end gap-1">
                {isDropped ? (
                  <ActionButton sm title="恢复这个源文件" onClick={() => onToggle(f.name)}>
                    已剔除
                  </ActionButton>
                ) : (
                  <>
                    <ActionButton sm title={`下载 ${f.name}`}>
                      <Download className="size-3" />
                    </ActionButton>
                    <ActionButton
                      sm
                      title="从整包里剔除（不进后续阶段）"
                      onClick={() => onToggle(f.name)}
                    >
                      <MinusCircle className="size-3" />
                    </ActionButton>
                  </>
                )}
              </span>
            </li>
          )
        })}
      </ul>
    </WorkCard>
  )
}
