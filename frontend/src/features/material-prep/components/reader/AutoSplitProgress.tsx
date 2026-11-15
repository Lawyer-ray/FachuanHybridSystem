import { Loader2, TriangleAlert } from 'lucide-react'

import { engineLabel } from '../../draft'
import {
  STALE_SECONDS_LIMIT,
  formatElapsed,
  pipelineProgressPct,
  type JobProgressSnapshot,
} from './auto-split-helpers'
import type { EngineName } from '../../types'

/**
 * 自动分段任务进度面板：底部悬浮条。
 *
 * 为什么是底部浮条而不是嵌进工具条：整条流水线（云端取字 → 交叉比对 → LLM 分段）
 * 在 164 页真实卷宗上要 10-20 分钟，信息量远超一个按钮能承载的文字（当前在做什么、
 * 多少页、已经多久、有没有卡住）。塞进工具条会把它撑爆——手机 `max-[760px]` 下
 * `.mp-rd-toolbar` 是 46px 固定高度的横向滚动条。
 *
 * 用 `fixed` 而不参与三栏 flex 分配：中栏是 `flex-1 overflow-y-auto`，在它上面再
 * 叠一块会跟着内容一起滚、并让滚动高度计算变复杂。浮条贴底、与协作范式
 * （SelectionBar）一致，也不影响布局。z-[60] 与 SelectionBar 同级——两者都是
 * 底部浮条，选页汇总条只在选页后出现，不会与一个在跑的任务同时出现。
 */
export function AutoSplitProgress({
  snapshot,
  onDismiss,
}: {
  snapshot: JobProgressSnapshot
  /** 用户点「不再显示」：只从界面收起，**不**取消后端任务（一份 164 页卷宗要跑十几分钟） */
  onDismiss: () => void
}) {
  const stage = snapshot.stage
  const percent = pipelineProgressPct(stage, snapshot.progressPct)
  const elapsed = formatElapsed(snapshot.elapsedSeconds)
  // 心跳停了只**提示**、不替用户放弃：任务可能是别的浏览器发起的大卷宗，
  // 后端看门狗可能正在自动重排。误报中断会让律师亲手打断一个其实还能救的任务。
  const stale = snapshot.staleSeconds != null && snapshot.staleSeconds > STALE_SECONDS_LIMIT
  const engines = engineNames(snapshot.dualEngines)
  const source = snapshot.sourceName ? `（${snapshot.sourceName}）` : ''

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="auto-split-progress"
      className="fixed bottom-4 left-1/2 z-[60] w-[min(460px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-border bg-card px-4 py-2.5 shadow-2xl max-[760px]:w-[calc(100vw-16px)] max-[760px]:px-3"
    >
      <div className="flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 flex-none animate-spin text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{stageText(snapshot, engines)}</span>
        {/* 百分比与进度条分离：`tabular-nums` 让数字跳动时整行不跟着左右抖 */}
        <span className="flex-none text-[12px] tabular-nums text-muted-foreground">{percent}%</span>
      </div>

      {/* 进度条：阶段映射见 `pipelineProgressPct`。取字阶段后端 progress 已到 100
          时这里只到 90——否则界面会停在「100%」十几分钟不动，看起来像假死。 */}
      <div
        className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-secondary"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label="自动分段进度"
      >
        <div
          className="h-full rounded-full bg-zinc-900 transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="mt-1.5 flex items-center gap-2 text-[11.5px] text-muted-foreground">
        {/* 秒级刷新才有「在动」的感觉，所以一律显示已耗时；拿不到就不占位 */}
        {elapsed && <span className="tabular-nums">已用 {elapsed}</span>}
        {elapsed && <span aria-hidden>·</span>}
        <span className="min-w-0 flex-1 truncate">{source || '本次识别'}</span>
        <button
          type="button"
          onClick={onDismiss}
          title="隐藏进度（不会取消后台任务，重新打开材料包会再次显示）"
          className="flex-none text-[11.5px] text-secondary-foreground hover:underline"
        >
          不再显示
        </button>
      </div>

      {stale && (
        <p className="mt-1.5 flex items-start gap-1 text-[11.5px] leading-4 text-amber-700">
          <TriangleAlert className="mt-[2px] h-3 w-3 flex-none" aria-hidden />
          <span>
            已 {formatStale(snapshot.staleSeconds)}无响应，可能已中断
          </span>
        </p>
      )}
    </div>
  )
}

/**
 * 「现在在做什么」。
 *
 * 取字阶段报页数（那是唯一有真实页级的阶段）；交叉比对要报引擎名——律师花两份
 * 云端费用就是为了这一步，看不见它在跑会以为钱白花了。
 */
function stageText(snapshot: JobProgressSnapshot, engines: string[] = engineNames(snapshot.dualEngines)): string {
  switch (snapshot.stage) {
    case 'cross_check':
      return engines.length > 0 ? `双引擎交叉比对中：${engines.join(' × ')}` : '双引擎交叉比对中'
    case 'segment':
      return '正在智能分段'
    case 'done':
      return '收尾中'
    default:
      return snapshot.totalPages > 0
        ? `正在识别文字（${snapshot.processedPages}/${snapshot.totalPages} 页）`
        : '正在识别文字'
  }
}

/** 心跳停了多久。不足一分钟别写「已 0 分钟」（阈值是 12 分钟，只是防御） */
function formatStale(seconds: number | null): string {
  if (seconds == null || seconds < 60) return `${Math.max(0, Math.round(seconds ?? 0))} 秒`
  if (seconds < 90) return '1 分钟'
  return `${Math.round(seconds / 60)} 分钟`
}

/**
 * `dual_engines`（逗号分隔的引擎码）→ 中文引擎名。
 *
 * 走 `engineLabel` 而不是本地再写一份：引擎码 → 人话必须只有一处，
 * 否则「勾了 PaddleOCR-VL」与「分歧里写着 paddleocr_vl」迟早对不上。
 */
function engineNames(dualEngines: string): string[] {
  return dualEngines
    .split(',')
    .map((code) => code.trim())
    .filter(Boolean)
    .map((code) => engineLabel(code as EngineName))
}
