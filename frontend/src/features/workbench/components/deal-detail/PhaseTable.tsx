import { useEffect, useRef, useState, type MouseEvent } from 'react'

import { cn } from '@/lib/utils'
import { deliverableStateLabel, phaseMetaText, phaseStateLabel } from './special-phase-state'
import {
  flattenTree,
  type FlatPhase,
  type PhaseDeliverable,
  type PhaseNode,
  type PhaseState,
} from './special-phase-tree'

/**
 * 阶段与交付物 = 真正的 `<table>`（54 号原型第十六～十七轮的最终形态）。
 *
 * **为什么必须是 table，而不是 flex/grid**：要的是「日期 / 交付物 / 版本 / 状态
 * 四列在**所有层级**上竖着对齐」。原型试过 6 种 flex/grid 方案全部失败——只要阶段行
 * 与文件行的内容不同（阶段行多「＋ 起草」），列就会错开 11px（1fr 按内容最小宽度算、
 * padding 累积）。`table-layout: fixed` 下列宽由浏览器统一分配，与单元格内容无关。
 *
 * **为什么不渲染表头**：四列语义自明，表头只在第一层出现一次反而不完整。列本身保留。
 *
 * 交互约定：
 * - 整行 `<tr>` 是点击目标（不用 `absolute inset-0` 的遮罩按钮——它会挡住日期文字的选中）；
 * - 阶段名**单击不折叠**（双击是就地改名），单击行内其余位置才折叠/展开；
 * - 点交付物 → 就地展开文档（由父级把 subpath 交给 FilePreviewCard），不跳页。
 */
export function PhaseTable({
  tree,
  fileCountOf,
  onToggle,
  onRename,
  onOpenDeliverable,
  onDraft,
}: {
  tree: PhaseNode[]
  /** 阶段目录里已有文件数（元信息「N 个文件」用） */
  fileCountOf: (node: PhaseNode) => number
  onToggle: (key: string) => void
  onRename: (key: string, name: string) => void
  /** 点交付物 → 就地预览（有实际文件的才有 subpath） */
  onOpenDeliverable: (d: PhaseDeliverable) => void
  /** 阶段行尾「＋ 起草」（窄屏隐藏） */
  onDraft: (key: string) => void
}) {
  const [renaming, setRenaming] = useState<{ key: string; value: string } | null>(null)
  const rows = flattenTree(tree)

  const commitRename = () => {
    if (!renaming) return
    const value = renaming.value.trim()
    if (value) onRename(renaming.key, value)
    setRenaming(null)
  }

  return (
    <table className="ptree w-full table-fixed border-collapse">
      <colgroup>
        <col className="w-[82px] max-[900px]:w-[56px]" />
        <col />
        <col className="w-[52px] max-[900px]:hidden" />
        <col className="w-[196px] max-[900px]:w-[76px]" />
      </colgroup>
      <tbody>
        {rows.map((item) => {
          const p = item.node
          const files = p.deliverables
          const expandable = p.folders.length > 0 || files.length > 0
          const open = p.open && expandable
          return (
            <PhaseRows
              key={p.key}
              item={item}
              open={open}
              expandable={expandable}
              fileCount={fileCountOf(p)}
              renaming={renaming?.key === p.key ? renaming : null}
              onStartRename={() => setRenaming({ key: p.key, value: p.name })}
              onRenameChange={(value) => setRenaming({ key: p.key, value })}
              onRenameCommit={commitRename}
              onRenameCancel={() => setRenaming(null)}
              onToggle={() => onToggle(p.key)}
              onDraft={() => onDraft(p.key)}
              onOpenDeliverable={onOpenDeliverable}
            />
          )
        })}
      </tbody>
    </table>
  )
}

/** 阶段行 +（展开时）它的交付物行。同一张表里，列自然对齐 */
function PhaseRows({
  item,
  open,
  expandable,
  fileCount,
  renaming,
  onStartRename,
  onRenameChange,
  onRenameCommit,
  onRenameCancel,
  onToggle,
  onDraft,
  onOpenDeliverable,
}: {
  item: FlatPhase
  open: boolean
  expandable: boolean
  fileCount: number
  renaming: { key: string; value: string } | null
  onStartRename: () => void
  onRenameChange: (value: string) => void
  onRenameCommit: () => void
  onRenameCancel: () => void
  onToggle: () => void
  onDraft: () => void
  onOpenDeliverable: (d: PhaseDeliverable) => void
}) {
  const p = item.node
  const files = p.deliverables
  const indent = (item.depth - 1) * 18
  /**
   * 行点击 = 展开/折叠。
   *
   * 难点：阶段名既是「单击折叠」区域，又是「双击改名」目标。此前这里直接
   * `if (closest('[data-rename]')) return` 把名字上的点击全放过去了，结果
   * **点是阶段名就不折叠**（律师直觉上一定会点名）。
   *
   * 现在用 220ms 延时区分：单击→折叠；期间来了第二次 click（双击）→撤销折叠，
   * 交给 dblclick 去进改名态。延迟阈值取系统双击间隔的常见值，短于它不显迟钝。
   */
  const clickTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onRowClick = (e: MouseEvent<HTMLTableRowElement>) => {
    if (!expandable) return
    const onName = !!(e.target as HTMLElement).closest('[data-rename]')
    if (!onName) {
      onToggle()
      return
    }
    if (clickTimer.current) {
      clearTimeout(clickTimer.current)
      clickTimer.current = null
      return
    }
    clickTimer.current = setTimeout(() => {
      clickTimer.current = null
      onToggle()
    }, 220)
  }
  useEffect(
    () => () => {
      if (clickTimer.current) clearTimeout(clickTimer.current)
    },
    [],
  )

  return (
    <>
      <tr
        data-phase-row={p.key}
        data-depth={item.depth}
        aria-expanded={open}
        onClick={onRowClick}
        className={cn(
          'border-t border-border-light first:border-t-0',
          item.depth === 1 && 'border-t-border',
          expandable ? 'cursor-pointer' : 'cursor-default',
          'hover:bg-secondary/45',
          item.depth === 2 && 'bg-secondary/20',
          item.depth === 3 && 'bg-secondary/32',
        )}
      >
        <td className="h-9 pl-5 align-middle max-[900px]:pl-3">
          <span className={cn('text-[12px] whitespace-nowrap tabular-nums', p.startDate ? 'text-muted-foreground' : 'text-muted-foreground/55')}>
            {p.startDate ? p.startDate.slice(5) : p.state === 'todo' ? '未开始' : '—'}
          </span>
        </td>
        <td className="overflow-hidden align-middle">
          <span className="group/phase flex items-center">
            <span className="block shrink-0" style={{ width: indent }} />
            <PhaseChevron open={open} blank={!expandable} />
            {renaming ? (
              <RenameInput
                value={renaming.value}
                onChange={onRenameChange}
                onCommit={onRenameCommit}
                onCancel={onRenameCancel}
              />
            ) : (
              <span
                data-rename={p.key}
                title="双击改名"
                onDoubleClick={(e) => {
                  e.stopPropagation()
                  onStartRename()
                }}
                className={cn(
                  // **必须 flex-1**：本行其余兄弟都是 shrink-0，若不显式让名字
                  // 吃掉剩余空间，min-w-0 + truncate 会把它压成 0 宽——文字
                  // 在 DOM 里存在却完全看不见（实测 width:0，整列空白）。
                  'min-w-0 flex-1 truncate text-[13.5px] font-[600] tracking-[-0.005em]',
                  p.state === 'doing' ? 'font-[700] text-foreground' : p.state === 'todo' ? 'text-secondary-foreground/62' : 'text-secondary-foreground',
                  item.depth > 1 && 'text-[13px] font-[550]',
                )}
              >
                {p.name}
              </span>
            )}
            <span className="ml-2.5 shrink-0 text-[11.5px] whitespace-nowrap text-muted-foreground/62 tabular-nums max-[900px]:hidden">
              {phaseMetaText(p.folders.length, fileCount)}
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onDraft()
              }}
              className={cn(
                'ml-2.5 shrink-0 cursor-pointer text-[11.5px] text-muted-foreground transition-opacity hover:text-foreground max-[900px]:hidden',
                // 壳层用 group/phase 做 hover 可见：非当前阶段收着，悬停或键盘聚焦时显形
                p.state === 'doing' ? 'opacity-100' : 'opacity-0 group-hover/phase:opacity-100 focus-visible:opacity-100',
              )}
            >
              ＋ 起草
            </button>
          </span>
        </td>
        <td className="align-middle max-[900px]:hidden" />
        <td className="overflow-hidden pr-5 text-right whitespace-nowrap align-middle max-[900px]:pr-3">
          <StateTag state={p.state ?? 'todo'} />
        </td>
      </tr>

      {open && files.length === 0 && p.folders.length === 0 && (
        <tr className="border-t border-border-light">
          <td />
          <td className="overflow-hidden">
            <span className="flex items-center">
              <span className="block shrink-0" style={{ width: indent + 18 }} />
              <span className="text-[12px] text-muted-foreground/60">暂无交付物</span>
            </span>
          </td>
          <td className="max-[900px]:hidden" />
          <td />
        </tr>
      )}

      {open &&
        files.map((d) => (
          <tr key={d.id} data-file-row={d.id} className={cn('h-[30px] border-t border-border-light hover:bg-secondary/30', d.planned && 'pending')}>
            <td className="h-[30px] pl-5 align-middle max-[900px]:pl-3">
              <span className="text-[12px] whitespace-nowrap text-muted-foreground tabular-nums">{d.date ? d.date.slice(5) : '—'}</span>
            </td>
            <td className="overflow-hidden align-middle">
              <span className="flex items-center">
                <span className="block shrink-0" style={{ width: indent + 18 }} />
                {d.subpath ? (
                  <button
                    type="button"
                    title={d.subpath}
                    onClick={() => onOpenDeliverable(d)}
                    className="min-w-0 cursor-pointer truncate text-left text-[12.5px] text-secondary-foreground underline decoration-border underline-offset-[3px] transition-colors hover:text-foreground"
                  >
                    {d.name}
                    {d.state === 'doing' ? ' ↗' : ''}
                  </button>
                ) : (
                  <span
                    title="计划中的交付物，还没有文件"
                    className="min-w-0 truncate text-[12.5px] text-muted-foreground/80"
                  >
                    {d.name}
                  </span>
                )}
              </span>
            </td>
            <td className="align-middle max-[900px]:hidden">
              {d.version ? <span className="text-[11.5px] text-muted-foreground tabular-nums">{d.version}</span> : null}
            </td>
            <td className="overflow-hidden pr-5 text-right whitespace-nowrap align-middle max-[900px]:pr-3">
              <span className={cn('text-[11.5px] font-[550]', fileStateClass(d))}>{deliverableStateLabel(d)}</span>
            </td>
          </tr>
        ))}
    </>
  )
}

/** 折叠三角：CSS 三角（尺寸与字号脱钩，不拉低全页最小字号） */
function PhaseChevron({ open, blank }: { open: boolean; blank: boolean }) {
  return (
    <span
      aria-hidden
      className={cn('relative mr-1.5 flex w-3.5 shrink-0 justify-center', blank && 'invisible')}
      style={{ fontSize: 0 }}
    >
      <span
        className="block h-0 w-0 border-y-4 border-l-[5px] border-y-transparent border-l-muted-foreground/55 transition-transform"
        style={{ transform: open ? 'rotate(90deg)' : undefined }}
      />
    </span>
  )
}

/** 就地改名输入框（Enter 提交 / Esc 取消 / 失焦提交） */
function RenameInput({
  value,
  onChange,
  onCommit,
  onCancel,
}: {
  value: string
  onChange: (v: string) => void
  onCommit: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLInputElement | null>(null)
  return (
    <input
      ref={ref}
      autoFocus
      onFocus={(e) => e.currentTarget.select()}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onBlur={onCommit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur()
        }
        if (e.key === 'Escape') {
          e.preventDefault()
          onCancel()
        }
      }}
      className="min-w-[120px] max-w-[320px] shrink-0 rounded-[6px] border border-ring bg-card px-1.5 py-0.5 text-[13.5px] font-[660] text-foreground outline-none"
    />
  )
}

/** 阶段状态：6px 圆点 + 文字（不是 pill——pill 是「系统给的结论」，这里是推进事实） */
function StateTag({ state }: { state: PhaseState }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-[5px] text-[11.5px] font-[550]',
        state === 'doing' ? 'font-[650] text-foreground' : state === 'todo' ? 'text-muted-foreground/55' : 'text-muted-foreground/85',
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          state === 'doing' ? 'bg-foreground' : state === 'done' ? 'bg-muted-foreground/55' : 'bg-border',
        )}
      />
      {phaseStateLabel(state)}
    </span>
  )
}

function fileStateClass(d: PhaseDeliverable): string {
  if (d.planned || d.state === 'todo') return 'text-muted-foreground/55'
  if (d.state === 'doing') return 'font-[650] text-foreground'
  return 'text-muted-foreground/85'
}
