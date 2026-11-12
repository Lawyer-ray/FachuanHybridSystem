import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { isPackStage, type PrepStage } from '../stages'
import { InboxView } from '../inbox'
import type { InboxSourceFilter } from '../inbox/types'
import type { InboxMessage, PackStatus } from '../types'
import { PackGrid } from './PackGrid'
import type { DeskViewMode } from './desk-toolbar-types'

type Tab = PackStatus

/**
 * 预处理页卡片容器的**卡身**：工具栏是卡的表头，这块是内容区，两者同属一张卡。
 *
 * 四个阶段共用一个容器、只换内容——收件箱视图 / 加载占位 / 错误 / 材料包网格。
 * 这里只收值与回调，不持有任何状态：阶段、筛选、离场标记的真值都在 DeskPage。
 */
export function DeskMainArea({
  stage,
  tab,
  viewMode,
  source,
  onSourceChange,
  search,
  onSearchChange,
  unreadOnly,
  onUnreadOnlyChange,
  isLoading,
  error,
  visible,
  leaving,
  gridRef,
  wrapRef,
  ringRef,
  onOpen,
  onReject,
  onAccept,
  onRename,
  onDelete,
}: {
  stage: PrepStage
  tab: Tab
  viewMode: DeskViewMode
  source: InboxSourceFilter
  onSourceChange: (s: InboxSourceFilter) => void
  search: string
  onSearchChange: (v: string) => void
  unreadOnly: boolean
  onUnreadOnlyChange: (v: boolean) => void
  isLoading: boolean
  error: unknown
  visible: InboxMessage[]
  leaving: Record<number, 'left' | 'right'>
  gridRef: React.RefObject<HTMLDivElement | null>
  wrapRef: React.RefObject<HTMLDivElement | null>
  ringRef: React.RefObject<HTMLDivElement | null>
  onOpen: (index: number) => void
  onReject: (p: InboxMessage) => void
  onAccept: (p: InboxMessage) => void
  onRename: (p: InboxMessage) => void
  onDelete: (p: InboxMessage) => void
}) {
  return (
    // 阶段切换的淡入：key={stage} 确保换阶段时这层重挂，
    // app-stage-enter 才会重新播一次。不加 key 时 React 复用同一节点，
    // 过渡不会触发，表现为主区域内容硬切（2026-11-04 反馈「切换不自然」）。
    // 只给主区域而不给整页：页签不该跟着一起淡，它应该保持常驻。
    // 注意它**在卡片容器内部**：工具栏是卡的表头、这块是卡身，
    // 两者必须同属一张卡，否则页面上会出现两张上下叠放的黑框。
    <div
      key={stage}
      className="app-stage-enter flex min-h-0 flex-1 flex-col overflow-y-auto"
    >
      {!isPackStage(stage) ? (
        /* 收件箱阶段：主区域交给 InboxView（受控：筛选值来自页面工具栏）。
           拖放层仍在外层生效——把文件拖进收件箱页时照旧建包并跳到「待处理」。 */
        <InboxView
          source={source}
          onSourceChange={onSourceChange}
          search={search}
          onSearchChange={onSearchChange}
          unreadOnly={unreadOnly}
          onUnreadOnlyChange={onUnreadOnlyChange}
        />
      ) : isLoading ? (
        /* 与 PackGrid 的空态同构：列表区占位而非整页 loading——页签仍在，
           所以居中要相对卡片区（LoadingBlock 自带 justify-center）。
           虚线框靠调用点补：加载态与空态要共用一个框，看起来是同块区域换内容 */
        <LoadingBlock
          text="加载材料包…"
          className="m-4 rounded-[13px] border border-dashed border-zinc-300 py-16"
        />
      ) : error ? (
        /* 前缀「无法加载材料包：」留在调用点的原因：ErrorBlock 只把 error 的
           message 原样倒出，而这里要说明白是哪块数据挂了。
           fallback 取「未知错误」——旧实现就在 message 缺失时显示它，不改文案。 */
        <div className="space-y-1.5 p-4">
          <p className="text-sm text-destructive">无法加载材料包：</p>
          <ErrorBlock error={error} fallback="未知错误" className="px-4 py-6 text-sm" />
        </div>
      ) : (
        <PackGrid
          gridRef={gridRef}
          wrapRef={wrapRef}
          ringRef={ringRef}
          packs={visible}
          tab={tab}
          leaving={leaving}
          onOpen={onOpen}
          onReject={onReject}
          onAccept={onAccept}
          onRename={onRename}
          onDelete={onDelete}
          viewMode={viewMode}
        />
      )}
    </div>
  )
}
