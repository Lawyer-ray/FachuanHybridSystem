import { memo } from 'react'
import { FileText, FolderOpen, Pencil, Trash2 } from 'lucide-react'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { EmptyBlock } from '@/components/shared/AsyncState'
import { cn } from '@/lib/utils'
import { friendlyTime } from '@/lib/format'
import { PackCard } from './PackCard'
import type { InboxMessage, PackStatus } from '../types'
import type { DeskViewMode } from './desk-toolbar-types'

type Tab = PackStatus

/**
 * 材料包主区域：同一批 packs 的两种呈现（方案 B）。
 *
 * · grid：缩略图大卡片网格，靠图辨认是哪一包（`PackCard` 原样复用）
 * · list：紧凑单行列表，密度与收件箱列表对齐（约 py-2.5 / text-[13px]）
 *
 * 两种形态共用同一套外壳职责：`data-pack-idx`（键盘导航按序定位）、
 * 右键菜单（打开 / 重命名 / 删除）、离场动画（leave-left / leave-right）、
 * `ringRef`（useDeskRing 的高亮框挂点）——换形态不换这些契约。
 * 离场动画类挂在逐包容器上（两个形态都有），不依赖 PackCard 卡内：
 * 列表行不复用 PackCard，动画必须由这层给。
 */
export function PackGrid({
  gridRef,
  wrapRef,
  ringRef,
  packs,
  tab,
  viewMode,
  leaving,
  onOpen,
  onReject,
  onAccept,
  onRename,
  onDelete,
}: {
  gridRef: React.RefObject<HTMLDivElement | null>
  wrapRef: React.RefObject<HTMLDivElement | null>
  ringRef: React.RefObject<HTMLDivElement | null>
  packs: InboxMessage[]
  tab: Tab
  viewMode: DeskViewMode
  leaving: Record<number, 'left' | 'right'>
  onOpen: (index: number) => void
  onReject: (pack: InboxMessage) => void
  onAccept: (pack: InboxMessage) => void
  onRename: (pack: InboxMessage) => void
  onDelete: (pack: InboxMessage) => void
}) {
  return (
    <div className="relative p-4" ref={wrapRef}>
      <div
        ref={gridRef}
        className={
          viewMode === 'grid'
            ? 'grid grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-4'
            : 'flex flex-col'
        }
      >
        {packs.map((p, i) => {
          const leave = leaving[p.id]
          const leaveCls = leave === 'right' ? 'leave-right' : leave === 'left' ? 'leave-left' : undefined
          return (
            <div
              key={p.id}
              data-pack-idx={i}
              className={cn(
                viewMode === 'list' && 'border-b border-border last:border-b-0',
                leaveCls,
              )}
            >
              <ContextMenu>
                <ContextMenuTrigger className="block w-full">
                  {viewMode === 'grid' ? (
                    /* 逐卡回调透传父级 props（引用稳定），index/pack 的闭包下沉到 PackCard 内部，memo 才能命中。
                       离场动画由外层容器统一承担，这里不再传 leaving——否则同一动画挂两层 */
                    <PackCard
                      pack={p}
                      index={i}
                      finished={p.segs > 0 && p.named === p.segs}
                      onOpen={onOpen}
                      onReject={onReject}
                      onAccept={onAccept}
                    />
                  ) : (
                    <PackRow
                      pack={p}
                      index={i}
                      finished={p.segs > 0 && p.named === p.segs}
                      onOpen={onOpen}
                      onReject={onReject}
                      onAccept={onAccept}
                    />
                  )}
                </ContextMenuTrigger>
                <ContextMenuContent className="w-44">
                  <ContextMenuItem onSelect={() => onOpen(i)}>
                    <FolderOpen /> 打开材料包
                  </ContextMenuItem>
                  <ContextMenuItem onSelect={() => onRename(p)}>
                    <Pencil /> 重命名材料包
                  </ContextMenuItem>
                  <ContextMenuSeparator />
                  <ContextMenuItem variant="destructive" onSelect={() => onDelete(p)}>
                    <Trash2 /> 删除材料包
                  </ContextMenuItem>
                </ContextMenuContent>
              </ContextMenu>
            </div>
          )
        })}

        {/* todo 页签的空态：只是一句提醒，不再放虚线新建槽。
            上传入口已由顶部「新建材料包」按钮 + 全局拖放层承担，网格里再来一个是重复入口 */}
        {packs.length === 0 && tab === 'todo' && (
          <EmptyBlock
            className={cn(
              'rounded-[13px] border border-dashed border-zinc-300 py-16 text-sm text-secondary-foreground',
              viewMode === 'grid' && 'col-span-full',
            )}
          >
            全部处理完了，拖入新材料，或点上方「新建材料包」
          </EmptyBlock>
        )}

        {packs.length === 0 && tab !== 'todo' && (
          /* 跨满整行（col-span-full）与虚线框留在调用点：这是网格里的占位格，
             共享件只管居中与灰字 */
          <EmptyBlock
            className={cn(
              'rounded-[13px] border border-dashed border-zinc-300 py-16 text-sm text-secondary-foreground',
              viewMode === 'grid' && 'col-span-full',
            )}
          >
            这里还没有{tab === 'done' ? '已归案' : '归档'}的材料包
          </EmptyBlock>
        )}
      </div>
      <div ref={ringRef} className="mp-ring" />
    </div>
  )
}

/** 列表形态的状态徽章文案与配色（与 PackCard 顶部标签同一套语义）。 */
function statusBadge(pack: InboxMessage, finished: boolean) {
  if (pack.status === 'done') return { text: '已归案', cls: 'border-green-200 bg-green-50 text-green-700' }
  if (pack.segs === 0) return { text: '未打开', cls: 'border-zinc-200 bg-zinc-50 text-secondary-foreground' }
  if (finished) return { text: '已归类', cls: 'border-green-200 bg-green-50 text-green-700' }
  return { text: `${pack.segs - pack.named} 份未归类`, cls: 'border-amber-200 bg-amber-50 text-amber-700' }
}

/**
 * 紧凑列表行：左缩略图标 / 中名称+状态+时间 / 右操作。
 *
 * 为什么不复用 `PackCard`：那张卡的结构（缩略纸堆带 148px + 标签层 + 进度条）
 * 就是卡片形态本身，列表要的是每分钟能扫几十行的高度；硬塞变体只会让两个
 * 形态都变得难读。数据取用的与卡片一致（name / 状态 / 进度 / 时间）。
 */
const PackRow = memo(function PackRow({
  pack,
  index,
  finished,
  onOpen,
  onReject,
  onAccept,
}: {
  pack: InboxMessage
  index: number
  finished: boolean
  onOpen: (index: number) => void
  onReject: (pack: InboxMessage) => void
  onAccept: (pack: InboxMessage) => void
}) {
  const badge = statusBadge(pack, finished)
  const kinds = pack.types ?? []
  const restUnclassified = pack.segs - kinds.length
  const time = friendlyTime(pack.received_at, { fallback: pack.received_at, else: 'md' })

  return (
    <article className="mp-packet group relative flex items-center gap-3 px-3 py-2.5 text-[13px] transition-colors hover:bg-secondary">
      {/* 打开材料包的拉伸点击层：整行可点、键盘可达，交互按钮再抬 z 压上去 */}
      <button
        type="button"
        onClick={() => onOpen(index)}
        aria-label={`打开材料包：${pack.subject || `材料包 ${pack.id}`}`}
        className="absolute inset-0 z-[1] cursor-pointer"
      />

      {/* 左：小缩略（文件图标；有上传合同时用琥珀色点明） */}
      <span
        className={cn(
          'grid h-8 w-8 flex-none place-items-center rounded-[7px] border bg-secondary text-secondary-foreground',
          pack.upload_contract_name ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-border',
        )}
      >
        <FileText className="h-4 w-4" />
      </span>

      {/* 中：名称 + 状态 + 类型 + 时间 */}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <h3 className="min-w-0 truncate text-[13px] font-medium tracking-tight">
            {pack.subject || `材料包 ${pack.id}`}
          </h3>
          <span className={cn('flex-none rounded-full border px-1.5 py-[1px] text-[10.5px] font-medium', badge.cls)}>
            {badge.text}
          </span>
        </div>
        <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <span className="flex-none tabular-nums">{time}</span>
          {pack.pages > 0 && (
            <>
              <span className="h-[3px] w-[3px] flex-none rounded-full bg-zinc-300" />
              <span className="flex-none tabular-nums">{pack.pages} 页</span>
            </>
          )}
          {(kinds.length > 0 || restUnclassified > 0) && (
            <>
              <span className="h-[3px] w-[3px] flex-none rounded-full bg-zinc-300" />
              <span className="min-w-0 truncate">
                {kinds.join(' · ')}
                {restUnclassified > 0 && `${kinds.length > 0 ? ' · ' : ''}+${restUnclassified} 份未归类`}
              </span>
            </>
          )}
        </div>
      </div>

      {/* 右：操作（z 抬到拉伸点击层之上，否则按钮点不到） */}
      <span className="relative z-[2] flex flex-none items-center gap-[6px]">
        <button
          type="button"
          onClick={() => onReject(pack)}
          title="不接：已归档留痕，未建案"
          className="h-[27px] flex-none rounded-[7px] border border-transparent bg-transparent px-2.5 text-[12px] font-medium text-secondary-foreground transition-colors hover:border-border hover:bg-card hover:text-foreground"
        >
          不接
        </button>
        <button
          type="button"
          onClick={() => onAccept(pack)}
          disabled={!finished}
          title={finished ? '归案：绑定案件后进入办案流程' : '先完成拆分与归类'}
          className={cn(
            'h-[27px] flex-none rounded-[7px] border px-2.5 text-[12px] font-medium transition-colors',
            finished
              ? 'border-border bg-card text-foreground group-hover:border-foreground group-hover:bg-foreground group-hover:text-background'
              : 'cursor-not-allowed border-border bg-card text-foreground opacity-40',
          )}
        >
          归案
        </button>
      </span>
    </article>
  )
})
