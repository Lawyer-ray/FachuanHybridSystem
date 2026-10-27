import { ChevronRight, FileText, Plus } from 'lucide-react'
import { useState } from 'react'

import { EmptyBlock } from '@/components/shared/AsyncState'
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
  /** 事项自己的目录（来自文件夹扫描时给出），用于展开取交付物 */
  subpath?: string
  /** 该事项目录下的交付物数量；undefined = 未统计（尚未展开过） */
  fileCount?: number
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

/** 单行：事项 + 可展开的交付物清单 */
function ItemRow({
  it,
  loadFiles,
  onOpenDeliverable,
}: {
  it: ServiceItem
  loadFiles?: (subpath: string) => Promise<Array<{ name: string; subpath: string; size: number }>>
  onOpenDeliverable?: (f: { subpath: string; name: string }) => void
}) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<Array<{ name: string; subpath: string; size: number }> | null>(null)
  const [loading, setLoading] = useState(false)
  const expandable = !!loadFiles && !!it.subpath && (it.fileCount ?? 0) > 0

  const toggle = async () => {
    if (!expandable || !loadFiles || !it.subpath) return
    if (open) {
      setOpen(false)
      return
    }
    setOpen(true)
    if (files) return
    setLoading(true)
    try {
      setFiles(await loadFiles(it.subpath))
    } catch {
      setFiles([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <tr
        className={
          'border-t border-border-light ' +
          (expandable ? 'cursor-pointer hover:bg-secondary/40' : 'hover:bg-secondary/20')
        }
        onClick={() => void toggle()}
      >
        <td
          className={
            // whitespace-nowrap：日期是 `2026-10-17` 这类不可断的短串，允许换行
            // 会把它拆成两行（列宽被浏览器按内容比例压时必然发生），读起来断成两截
            'whitespace-nowrap px-5 py-2.5 align-baseline text-[12.5px] tabular-nums ' +
            (it.today ? 'font-[650] text-status-red' : 'text-muted-foreground')
          }
        >
          {/* 完整日期：截成 06-09 会丢掉年份，跨年度服务期（如 2026-03 至
              2027-03）里同一月日可能指两年，必须带年 */}
          {it.date || '—'}
          {it.today && <div className="text-[10.5px]">今天</div>}
        </td>
        <td className="py-2.5 align-baseline">
          <span className="whitespace-nowrap rounded-[5px] border border-border bg-secondary px-1.5 py-[1px] text-[10.5px] font-[620] text-secondary-foreground">
            {it.kind}
          </span>
        </td>
        <td className="py-2.5 align-baseline">
          <div className="flex items-center gap-1 font-[620]">
            {expandable && (
              <ChevronRight
                className={'size-3 flex-none text-muted-foreground transition-transform ' + (open ? 'rotate-90' : '')}
              />
            )}
            {it.title || <span className="text-muted-foreground/70">未命名事项</span>}
          </div>
          {it.detail && <div className="mt-0.5 text-[11.5px] text-muted-foreground">{it.detail}</div>}
        </td>
        <td className="py-2.5 align-baseline">
          {it.fileCount ? (
            <span className="text-[12px] text-secondary-foreground">{it.fileCount} 个文件</span>
          ) : (
            <span className="text-[11.5px] text-muted-foreground/50">—</span>
          )}
        </td>
        <td className={'px-5 py-2.5 text-right align-baseline text-[11.5px] font-[600] ' + STATUS_CLS[it.status]}>
          {STATUS_LABEL[it.status]}
        </td>
      </tr>

      {open && (
        <tr className="border-t border-border-light bg-secondary/20">
          <td />
          <td colSpan={4} className="py-2 pr-5">
            {loading ? (
              <span className="text-[11.5px] text-muted-foreground">读取交付物…</span>
            ) : files && files.length > 0 ? (
              <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                {files.map((f) => (
                  <button
                    key={f.subpath}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onOpenDeliverable?.({ subpath: f.subpath, name: f.name })
                    }}
                    className="inline-flex max-w-[320px] items-center gap-1.5 text-left text-[12px] text-secondary-foreground transition-colors hover:text-foreground"
                    title={f.name}
                  >
                    <FileKindBadge name={f.name} />
                    <span className="truncate underline decoration-border underline-offset-[3px]">{f.name}</span>
                  </button>
                ))}
              </div>
            ) : (
              <span className="text-[11.5px] text-muted-foreground">该事项下没有文件（只有子目录或为空）</span>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export function ServiceItemStream({
  items,
  note,
  onAdd,
  sourceSubpath,
  candidates,
  onChangeSource,
  isLoading,
  loadFiles,
  onOpenDeliverable,
}: {
  items: ServiceItem[]
  /** 表尾说明（服务期范围等） */
  note?: string
  onAdd?: () => void
  /** 当前读的事项源目录（自动识别出来的「办案」或用户指定的） */
  sourceSubpath?: string | null
  /** 可选的候选源目录（根层子目录） */
  candidates?: Array<{ name: string; subpath: string }>
  /** 换一个事项源目录；传 null 表示回到自动识别 */
  onChangeSource?: (subpath: string | null) => void
  isLoading?: boolean
  /**
   * 展开某事项时取交付物（懒加载）。不传则事项行不可展开。
   *
   * 做成回调而不是一次性全量预取：一份顾问合同常有 30+ 事项，全取就是
   * 30 次目录扫描；真正会被展开的通常只有一两个。
   */
  loadFiles?: (subpath: string) => Promise<Array<{ name: string; subpath: string; size: number }>>
  /** 点交付物文件 → 就地预览 */
  onOpenDeliverable?: (f: { subpath: string; name: string }) => void
}) {
  return (
    <div className="rounded-[12px] border border-border bg-card shadow-sm">
      <div className="flex items-center gap-2.5 px-5 pt-3.5">
        <b className="text-[14px] font-[680]">服务事项</b>
        <span className="rounded-full bg-secondary px-2 text-[11px] font-[600] leading-[18px] text-muted-foreground tabular-nums">
          {items.length}
        </span>
        {/* 标题区只留选择器：目录名已在选择器里显示，再写一遍「本年度 · 3-办案」
            是同一信息说两遍；「本年度」由下方 note 的服务期范围表达更准确 */}

        {onChangeSource && candidates && candidates.length > 0 && (
          <select
            value={sourceSubpath ?? ''}
            onChange={(e) => onChangeSource(e.target.value || null)}
            title="事项从哪个目录读取（目录名即事项名，前缀日期即发生日）"
            className="h-[24px] max-w-[160px] cursor-pointer truncate rounded-[6px] border border-border bg-card px-1.5 text-[11px] text-secondary-foreground"
          >
            <option value="">自动（找「办案」目录）</option>
            {candidates.map((c) => (
              <option key={c.subpath} value={c.subpath}>
                {c.name}
              </option>
            ))}
          </select>
        )}
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
        <EmptyBlock className="px-5 py-6 text-[12.5px] leading-relaxed">
          {isLoading ? (
            '正在读取事项目录…'
          ) : sourceSubpath ? (
            '该目录下还没有事项。按「日期-事项」建子文件夹，这里就会自动列出来。'
          ) : (
            <>
              没有找到「办案」目录。
              <br />
              在上方下拉里指定一个事项目录，或在合同文件夹里新建「3-办案」。
            </>
          )}
        </EmptyBlock>
      ) : (
        <table className="mt-1 w-full table-fixed border-collapse text-[13px]">
          <thead>
            <tr className="text-[11px] text-muted-foreground/70">
              <th className="w-[116px] px-5 py-2 text-left font-[600] tracking-[0.03em]">日期</th>
              <th className="w-[68px] py-2 text-left font-[600] tracking-[0.03em]">类型</th>
              <th className="py-2 text-left font-[600] tracking-[0.03em]">事项</th>
              <th className="py-2 text-left font-[600] tracking-[0.03em]">交付物</th>
              <th className="w-[84px] px-5 py-2 text-right font-[600] tracking-[0.03em]">状态</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <ItemRow key={`${it.date}-${i}`} it={it} loadFiles={loadFiles} onOpenDeliverable={onOpenDeliverable} />
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
