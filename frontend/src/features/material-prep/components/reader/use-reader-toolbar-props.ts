import { toast } from 'sonner'

import { rotationTargetOf } from './rotation-target'
import { useReaderStoreFields } from './use-reader-store-fields'
import { countUnclassified, isAutoSegName } from '../../draft'
import type { DraftState } from '../../types'
import type { useAutoSplit } from './use-auto-split'

/**
 * 工具组 props 装配：顶栏（≥1100 内联）与窄屏独立一行**渲染同一份配置**，
 * 只在 `narrow` / `inline` 上不同，其余完全同源。
 *
 * 还有两个「守卫型」动作放在这里而不是组件里：切列数（窗口不够宽就点不动）
 * 与归案（没归完类就只提示、不开弹窗）。它们读的是同一批派生量
 * （maxCols / effCols / 未归类数），跟 props 装配天然是一件事。
 */
export function useReaderToolbarProps(params: {
  /** 同 useAssignLaunch：允许 null，使用处守卫 */
  draft: DraftState | null
  railOpen: boolean
  metaOpen: boolean
  onToggleRail: () => void
  onToggleMeta: () => void
  /** 多列时收起两侧栏（切到 1 列以上时布局要更宽敞） */
  onCollapsePanels: () => void
  /** 当前容器宽度下最多能并排几列 */
  maxColsAllowed: number
  effCols: number
  zoom: number
  zoomIn: () => void
  zoomOut: () => void
  onResetSegments: () => void
  onFocusSeg: (si: number) => void
  /** 「追加材料」按钮要触发的隐藏 input 元素（回调 ref 已由 Hook 落到自己的 ref 上） */
  addInput: HTMLInputElement | null
  /** 左栏当前选中段的下标（决定「转正」默认作用在哪一段） */
  focusedSeg: number
  autoSplit: ReturnType<typeof useAutoSplit>
}) {
  const {
    draft,
    railOpen,
    metaOpen,
    onToggleRail,
    onToggleMeta,
    onCollapsePanels,
    maxColsAllowed,
    effCols,
    zoom,
    zoomIn,
    zoomOut,
    onResetSegments,
    onFocusSeg,
    addInput,
    autoSplit,
  } = params

  // 直接取 store 里的稳定动作引用（zustand action 引用恒不变），不再每个 render
  // 新建箭头——否则工具栏 memo 失效
  const st = useReaderStoreFields()

  // 「转正」的作用范围（选中页 → 当前段 → 全部）：律师第一反应是「整份都倒了」，
  // 不该逼他先勾 37 页；而只放反一页时勾一页即可。落点写进标签，避免盲按。
  const rotationTarget = rotationTargetOf(draft, st.selPages, params.focusedSeg)

  // 归案唯一入口：没归完类不打开弹窗，跳到第一个未归类的段并提示
  //（未归类 = 名字仍是系统默认名；改名是唯一的归类入口）
  const handleAssign = () => {
    // 没草稿时归案无从谈起（bodyProps.draft 非空已由 Reader 保证，
    // 但 hook 参数类型允许 null，这里显式守卫）。
    if (!draft) {
      toast.info('材料包还在加载，请稍后再试')
      return
    }
    const unclassified = countUnclassified(draft)
    const allClassified = draft.segs.length > 0 && unclassified === 0
    if (!allClassified) {
      const first = draft.segs.findIndex((s) => isAutoSegName(draft, s))
      if (first >= 0) onFocusSeg(first)
      toast.info(`还有 ${unclassified} 份没命名 —— 双击左栏那行改名，或右键「重命名」`)
      return
    }
    st.setAssignOpen(true)
  }

  return {
    railOpen,
    metaOpen,
    onToggleRail,
    onToggleMeta,
    selMode: st.selMode,
    onToggleSelMode: st.toggleSelMode,
    onAddFiles: () => addInput?.click(),
    zoomVal: Math.round(zoom * 100),
    onZoomIn: zoomIn,
    onZoomOut: zoomOut,
    onZoomReset: () => st.setZoom(1),
    cols: effCols,
    maxCols: maxColsAllowed,
    // 窗口不够宽时菜单里只剩「单页」并说明原因，所以这里由 maxCols 派生，
    // 不单独维护一份布尔值（否则两个来源迟早对不上）
    colsDisabled: maxColsAllowed <= 1,
    // 菜单里点哪列就是哪列（旧的 1→2→3→1 循环在菜单里没有意义：
    // 三列时循环出的下一项是「1 列」，用户点「2 列」却拿到单页）
    onSetCols: (n: number) => {
      st.setCols(n)
      // 多列时收起侧栏，让页面更宽敞
      if (n > 1) onCollapsePanels()
    },
    onResetSegments,
    // 页转正（人工）：90 / -90 / 180 叠加，0 = 重置方向
    rotation: {
      label: rotationTarget.label,
      count: rotationTarget.refs.length,
      rotatedCount: rotationTarget.rotatedCount,
      rotate: (deg: number) => {
        if (!rotationTarget.refs.length) return
        if (deg === 0) st.resetPagesRotation(rotationTarget.refs)
        else st.rotatePages(rotationTarget.refs, deg)
      },
    },
    onAutoSplit: () => void autoSplit.run(),
    autoSplitRunning: autoSplit.running,
    autoSplitProgress: autoSplit.progress,
    layoutMode: st.layoutMode,
    onLayoutModeChange: st.setLayoutMode,
    cloudSelection: st.cloudSelection,
    onToggleCloudEngine: st.toggleCloudEngine,
    // 一键关闭交叉比对：回到自动容灾（不计比对费），选择随包保存
    onClearCrossCheck: () => st.setCloudSelection([]),
    handleAssign,
  }
}
