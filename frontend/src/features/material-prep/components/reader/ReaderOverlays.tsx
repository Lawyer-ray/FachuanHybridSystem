import type { Inconsistency, PageKey, PageQuality } from '../../types'
import { DocTodoDrawer } from './DocTodoDrawer'
import { InconsistencyDrawer } from './InconsistencyDrawer'
import { AutoSplitProgress } from './AutoSplitProgress'
import { SelectionBar } from './SelectionBar'
import type { JobProgressSnapshot } from './auto-split-helpers'

/** 自动分段任务会话态（结构由 use-auto-split-task 定义；这里只要面板用得到的那部分） */
export type AutoSplitTaskView = {
  jobId: string | null
  snapshot: JobProgressSnapshot | null
  /** 本页面亲自发起的任务（接管来的只展示、不回写草稿） */
  owned: boolean
}

/**
 * 阅读器上「浮在三栏之上」的抽屉与底栏：跨页不一致清单、证件页待补录、
 * 自动分段进度浮条、选页汇总条。
 *
 * 与 ReaderColumns 分开：这些不是布局的一部分（不进 flex 高度分配，也不给中栏的
 * overflow 加耦合），它们的开关态由 ReaderBody 持有，这里只负责渲染。
 */
export function ReaderOverlays({
  inconsistencyOpen,
  onInconsistencyOpenChange,
  inconsistencies,
  docTodoOpen,
  onDocTodoOpenChange,
  pageQuality,
  onGotoAnyPage,
  autoSplitTask,
  onHideAutoSplit,
  selPages,
  selCount,
  selCross,
  selRotatedCount = 0,
  onRotatePages,
  rotatedTotal = 0,
  onResetAllRotation,
  onClearSel,
  onApplySel,
}: {
  inconsistencyOpen: boolean
  onInconsistencyOpenChange: (open: boolean) => void
  inconsistencies: Inconsistency[]
  docTodoOpen: boolean
  onDocTodoOpenChange: (open: boolean) => void
  pageQuality: PageQuality | null
  onGotoAnyPage: (p: number) => void
  autoSplitTask: AutoSplitTaskView | null
  onHideAutoSplit?: () => void
  selPages: PageKey[]
  selCount: number
  selCross: boolean
  /** 所选页里已人工转正的有几页 */
  selRotatedCount?: number
  /** 批量转正（90/-90/180/0） */
  onRotatePages?: (deg: number) => void
  /** 全包已人工转正的页数（>0 才显示「全部重置」入口） */
  rotatedTotal?: number
  onResetAllRotation?: () => void
  onClearSel: () => void
  onApplySel: () => void
}) {
  return (
    <>
      {/* 全本跨页不一致清单：从左栏徽标打开，点页号直接跳到那一页 */}
      <InconsistencyDrawer
        open={inconsistencyOpen}
        onOpenChange={onInconsistencyOpenChange}
        items={inconsistencies}
        onGotoPage={onGotoAnyPage}
      />

      {/* 全卷证件页待补录：从左栏证件徽标打开，「查看原页」跳到那一页 */}
      <DocTodoDrawer
        open={docTodoOpen}
        onOpenChange={onDocTodoOpenChange}
        pageQuality={pageQuality}
        onGotoPage={onGotoAnyPage}
      />

      {/* 自动分段进度：底部浮条，与选页汇总条同一范式（不参与 flex 高度分配，
          不给中栏的 overflow 加滚动耦合）。没有快照时显示「准备中」——提交 164 页
          本身要几十秒，那段空白期也得有反馈。 */}
      {autoSplitTask &&
        (autoSplitTask.jobId || autoSplitTask.snapshot) && (
          <AutoSplitProgress
            snapshot={autoSplitTask.snapshot ?? pendingSnapshot(autoSplitTask.jobId)}
            onDismiss={onHideAutoSplit ?? (() => {})}
          />
        )}

      {/* 已转正提示 + 全部重置：只在真有旋转时出现。放在左下，避开中间的选页条
          与自动分段进度条；律师偶尔需要「我刚才转的都不对，全部回正」这个出口。 */}
      {rotatedTotal > 0 && onResetAllRotation && (
        <div className="fixed bottom-4 left-4 z-[60] flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11.5px] shadow-lg">
          <span className="text-muted-foreground">已转正 {rotatedTotal} 页</span>
          <button
            type="button"
            onClick={onResetAllRotation}
            className="rounded-[5px] px-1.5 py-0.5 text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            全部重置
          </button>
        </div>
      )}

      {/* 选页汇总条 */}
      {selPages.length > 0 && (
        <SelectionBar
          count={selCount}
          cross={selCross}
          rotatedCount={selRotatedCount}
          onClear={onClearSel}
          onApply={onApplySel}
          onRotate={onRotatePages}
        />
      )}
    </>
  )
}

/**
 * 刚提交、还没轮询到第一份快照时的占位：进度 0、阶段取字（面板据此显示
 * 「正在识别文字」）。与消费它的浮条放在一起——放到 auto-split-helpers.ts 会把
 * 那个文件从 348 行顶进 351–450 的软红线区间。
 */
function pendingSnapshot(jobId: string | null): JobProgressSnapshot {
  return {
    jobId: jobId ?? '',
    status: 'pending',
    stage: '',
    progressPct: 0,
    processedPages: 0,
    totalPages: 0,
    elapsedSeconds: null,
    staleSeconds: null,
    errorMessage: '',
    dualEngines: '',
    sourceName: '',
  }
}
