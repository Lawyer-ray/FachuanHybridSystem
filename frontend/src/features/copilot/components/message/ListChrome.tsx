/**
 * 转录列表的「外壳」控件：排队条、加载更早、回到底部。
 *
 * 三者都**不渲染任何消息**，只服务于列表这个容器的状态（排队名次、分页、
 * 滚动位置），所以从 `MessageList.tsx` 一并搬出来——留在主文件里会把
 * 「订阅 + 分组 + 吸底 + 锚点」的装配骨架冲散。纯搬运，行为与 DOM 逐字不变。
 */

import { Loader2 } from 'lucide-react'

/** 排队提示条：池满时显示名次（position 含自己，「前方 N 人」= N-1） */
export function QueueBanner({ position }: { position: number }) {
  const ahead = Math.max(0, position - 1)
  return (
    <div className="mb-2 flex items-center gap-1.5 rounded-[8px] border border-border bg-secondary/40 px-2.5 py-1.5 text-[12px] text-muted-foreground">
      <Loader2 className="h-3 w-3 flex-none animate-spin" />
      {ahead > 0 ? (
        <span>
          当前使用人数较多，排队中 · 前方 {ahead} 人…
        </span>
      ) : (
        <span>排队中，即将开始…</span>
      )}
    </div>
  )
}

/**
 * 「加载更早的消息」：只在显式上翻时加载（不做无限滚动——法庭笔录式的长会话里
 * 自动加载会让人丢掉正在读的位置）。是否显示由调用方判断（需要知道当前条数）。
 */
export function LoadOlderButton({
  loading,
  onLoad,
}: {
  loading: boolean
  /** store 的翻页 action（async）：内部 `void` 掉，不把 rejection 丢给事件系统 */
  onLoad: () => void | Promise<void>
}) {
  return (
    <div className="mb-2 flex justify-center">
      <button
        type="button"
        className="rounded-[8px] border border-border px-3 py-1 text-[12px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        onClick={() => void onLoad()}
        disabled={loading}
      >
        {loading ? '加载中…' : '加载更早的消息'}
      </button>
    </div>
  )
}

/**
 * 上翻看历史后一键回到最新：长回答（几十屏）里上翻后只能一直滚回去。
 * sticky bottom-0 让它只在本容器视野内吸底，不跟随页面其他区域。
 */
export function ScrollToBottomButton({ onClick }: { onClick: () => void }) {
  return (
    <div className="pointer-events-none sticky bottom-0 z-10 mt-2 flex justify-end">
      <button
        type="button"
        className="pointer-events-auto rounded-full border border-border bg-card px-2.5 py-1 text-[11.5px] text-muted-foreground shadow-sm transition-colors hover:text-foreground"
        title="跳到最新一条"
        onClick={onClick}
      >
        回到底部 ↓
      </button>
    </div>
  )
}
