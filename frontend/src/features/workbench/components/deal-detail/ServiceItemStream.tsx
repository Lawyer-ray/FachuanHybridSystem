import { FileText, Plus } from 'lucide-react'

import { FileKindBadge } from './FileKindBadge'

/**
 * 服务事项流：本服务期内「哪天、为什么、交付了什么」。
 *
 * **为什么用它替代「文件夹」当左栏主角**：文件夹只回答「文件在哪」，而常法
 * 顾问真正要回答的是「这一年我为他做了什么、哪些还没交付」。把事项按时间
 * 排成流，交付物挂在事项行上——文件从「目录树里的一个名字」变成「某项服务的
 * 产出」，这才是律师复盘的视角。
 *
 * 版式照 53 号原型：日期 → 类型 → 事项（含对象）→ 交付物 → 状态。
 * 用表格而非卡片流：一行一事项，便于竖扫；卡片会在 30+ 事项时变成一堵墙。
 */
export interface ServiceItem {
  /** 日期（yyyy-mm-dd） */
  date: string
  /** 今天（用于高亮「今天」那一行） */
  today?: boolean
  /** 类型标签：合同 / 开庭 / 咨询 / 归档… */
  kind: string
  /** 事项名 */
  title: string
  /** 对象/说明（当事人、标的、简要） */
  detail?: string
  /** 交付物（文件名 + 定位信息），点击就地预览 */
  deliverable?: { subpath: string; name: string }
  /** 状态 */
  status: 'done' | 'doing' | 'todo'
}

const STATUS_LABEL: Record<ServiceItem['status'], string> = {
  done: '已交付',
  doing: '进行中',
  todo: '待办',
}
const STATUS_CLS: Record<ServiceItem['status'], string> = {
  done: 'text-secondary-foreground/70',
  doing: 'text-foreground font-[700]',
  todo: 'text-muted-foreground/60',
}

export function ServiceItemStream({
  items,
  note,
  onOpenFile,
  onAdd,
}: {
  items: ServiceItem[]
  /** 表尾说明（服务期范围等） */
  note?: string
  onOpenFile?: (f: { subpath: string; name: string }) => void
  onAdd?: () => void
}) {
  return (
    <div className="rounded-[12px] border border-border bg-card shadow-sm">
      <div className="flex items-center gap-2.5 px-5 pt-3.5">
        <b className="text-[14px] font-[680]">服务事项</b>
        <span className="rounded-full bg-secondary px-2 text-[11px] font-[600] leading-[18px] text-muted-foreground tabular-nums">
          {items.length}
        </span>
        <span className="text-[11.5px] text-muted-foreground/70">本年度</span>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="ml-auto inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-border bg-card px-2.5 text-[11.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
          >
            <Plus className="size-3.5" />
            记事项
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="px-5 py-6 text-center text-[12.5px] text-muted-foreground">
          本服务期还没有服务事项。记一条，或在右栏合同文件夹里打开交付物。
        </div>
      ) : (
        <table className="mt-1 w-full border-collapse text-[13px]">
          <thead>
            <tr className="text-[11px] text-muted-foreground/70">
              <th className="w-[92px] px-5 py-2 text-left font-[600] tracking-[0.03em]">日期</th>
              <th className="w-[64px] py-2 text-left font-[600] tracking-[0.03em]">类型</th>
              <th className="py-2 text-left font-[600] tracking-[0.03em]">事项</th>
              <th className="py-2 text-left font-[600] tracking-[0.03em]">交付物</th>
              <th className="w-[76px] px-5 py-2 text-right font-[600] tracking-[0.03em]">状态</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={`${it.date}-${i}`} className="border-t border-border-light hover:bg-secondary/40">
                <td
                  className={
                    'px-5 py-2.5 align-baseline text-[12.5px] tabular-nums ' +
                    (it.today ? 'font-[650] text-status-red' : 'text-muted-foreground')
                  }
                >
                  {it.date.slice(5)}
                  {it.today && <div className="text-[10.5px]">今天</div>}
                </td>
                <td className="py-2.5 align-baseline">
                  <span className="whitespace-nowrap rounded-[5px] border border-border bg-secondary px-1.5 py-[1px] text-[10.5px] font-[620] text-secondary-foreground">
                    {it.kind}
                  </span>
                </td>
                <td className="py-2.5 align-baseline">
                  <div className="font-[620]">{it.title}</div>
                  {it.detail && <div className="mt-0.5 text-[11.5px] text-muted-foreground">{it.detail}</div>}
                </td>
                <td className="py-2.5 align-baseline">
                  {it.deliverable ? (
                    <button
                      type="button"
                      onClick={() => onOpenFile?.(it.deliverable!)}
                      className="inline-flex max-w-full items-center gap-1.5 text-left text-[12px] text-secondary-foreground transition-colors hover:text-foreground"
                      title={it.deliverable.name}
                    >
                      <FileKindBadge name={it.deliverable.name} />
                      <span className="truncate underline decoration-border underline-offset-[3px]">
                        {it.deliverable.name}
                      </span>
                    </button>
                  ) : (
                    <span className="text-[11.5px] text-muted-foreground/50">—</span>
                  )}
                </td>
                <td className={'px-5 py-2.5 text-right align-baseline text-[11.5px] font-[600] ' + STATUS_CLS[it.status]}>
                  {STATUS_LABEL[it.status]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {note && (
        <div className="border-t border-border-light px-5 py-2.5 text-[11.5px] text-muted-foreground">
          <FileText className="mr-1 inline size-3 align-[-2px]" />
          {note}
        </div>
      )}
    </div>
  )
}
