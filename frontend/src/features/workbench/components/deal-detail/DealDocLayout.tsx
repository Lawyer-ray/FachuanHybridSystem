import type { ReactNode } from 'react'

import { FilePreviewCard } from './FilePreviewCard'
import { ResizeHandle } from './ResizeHandle'
import { useResizablePanel } from './use-resizable-panel'

/** 净宽门槛：文档与事实卡并排至少要这么宽（低于它文档通栏、事实卡在其下） */
export const DOC_SIDE_BY_SIDE_MIN = 1100

/**
 * 未展开文档时的两栏栅格。
 *
 * **必须声明使用方名字**：此前写死成 `grid-cols-[minmax(0,1fr)_360px]`，
 * AI 助手抽屉占掉 600px、main 只有 840px 时，右栏 360 会把左栏压到 402px——
 * 阶段表格的「交付物」列只剩 70px，阶段名被挤成 0 宽（DOM 里有、屏上看不见）。
 * 所以三个断点都用「高净宽才两栏」，否则单列叠底。
 */
const COLUMNS_CLS =
  'grid items-start gap-[18px] grid-cols-1 ' +
  '@min-[820px]:grid-cols-[minmax(0,1fr)_320px] ' +
  '@min-[1100px]:grid-cols-[minmax(0,1fr)_340px] ' +
  '@min-[1400px]:grid-cols-[minmax(0,1fr)_360px] ' +
  '@min-[1760px]:grid-cols-[minmax(0,1fr)_400px] ' +
  '@min-[2200px]:grid-cols-[minmax(0,1fr)_440px]'

/** 正在就地预览的文件（null = 未展开） */
export interface PickedFile {
  subpath: string
  name: string
  size?: number
  modified_at?: string
  mtime?: number
}

/**
 * 就地编辑的三态布局（54 号原型「点交付物在当前页展开 OnlyOffice」）：
 *
 * | 形态 | 条件 | 布局 |
 * |---|---|---|
 * | ① 未展开 | `picked == null` | 左内容 + 右事实卡 |
 * | ② 文档在右 | 展开 + 净宽 ≥1100 | 左内容（事实卡退到左栏底部）+ 右文档 |
 * | ③ 文档通栏 | 展开 + 净宽 <1100 且宽屏 | 文档置顶通栏，内容与事实卡在其下 |
 *
 * **为什么门槛用「净宽」而不是容器查询**：助手是 fixed 抽屉，容器测不到它；宽屏
 * 下助手恒并排让位，主区会被压掉数百像素（见 use-net-width）。第 ③ 态下文档紧贴
 * 助手——律师此刻的注意力就是「左看文档右问 AI」，内容沉底滚动可达。
 *
 * 文档栏可拖拽调宽并记住偏好：只有事实卡时 360px 够用，装 OnlyOffice 时 A4 正文
 * 600px 以下就开始缩字，写死断点只能猜折中值。
 */
export function DealDocLayout({
  picked,
  docSideBySide,
  focusDoc,
  ownerId,
  onClose,
  onSaved,
  onReview,
  aside,
  /** 事实卡（未展开时在右栏；展开且文档在右时退到左栏底部；文档通栏时在内容下方） */
  rail,
  children,
}: {
  picked: PickedFile | null
  docSideBySide: boolean
  focusDoc: boolean
  ownerId: number
  onClose: () => void
  onSaved: () => void
  onReview: (f: { subpath: string; name: string }) => void
  /** 左栏内容（阶段表 / 服务事项流 + 下一程序） */
  children: ReactNode
  rail: ReactNode
  /** 右栏在未预览时的额外节（专项页的阶段派生目录） */
  aside?: ReactNode
}) {
  const panel = useResizablePanel({
    storageKey: 'fachuan:nonlit:preview-width',
    defaultWidth: 720,
    min: 360,
    maxRatio: 0.78,
  })
  // 解构出来用：直接把 hook 返回值对象挂在 JSX 上会被 react-hooks/refs 判成
  // 「渲染期读 ref」（它无法穿透对象判断哪些字段是 ref）
  const {
    containerRef,
    dragging,
    onPointerDown,
    setWidth,
    effectiveWidth,
  } = panel

  const doc = picked && (
    <div className="sticky top-[70px] flex h-[calc(100vh-100px)] min-h-[520px] flex-col">
      <FilePreviewCard kind="contract" ownerId={ownerId} file={picked} onClose={onClose} onSaved={onSaved} onReview={onReview} />
    </div>
  )

  return (
    <div
      ref={containerRef}
      className={
        picked
          ? docSideBySide
            ? 'flex items-start gap-[8px]'
            : 'flex flex-col gap-[18px]'
          : COLUMNS_CLS
      }
    >
      {focusDoc && <div className="min-w-0">{doc}</div>}

      <div className="min-w-0 flex-1 space-y-[18px]">
        {children}
        {picked && docSideBySide && rail}
      </div>

      {picked && docSideBySide && (
        <ResizeHandle
          dragging={dragging}
          hidden={false}
          onPointerDown={onPointerDown}
          onKeyAdjust={(dir) => setWidth((w) => Math.max(320, w + dir * 40))}
          label="调整预览栏宽度"
        />
      )}

      {!focusDoc && (
        <div
          className="min-w-0 space-y-[18px]"
          style={picked && effectiveWidth && docSideBySide ? { width: effectiveWidth, flex: 'none' } : undefined}
        >
          {picked ? doc : aside}
          {!picked && rail}
        </div>
      )}
    </div>
  )
}
