import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'
import type { FolderOwnerKind } from '../../api'
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
 *
 * 容器查询量的是**页面 main**（两页都必须带 `@container`）——视口量不到并排 AI
 * 助手让位掉的那几百像素。
 */
const COLUMNS_CLS =
  'grid items-start gap-[18px] grid-cols-1 ' +
  '@min-[820px]:grid-cols-[minmax(0,1fr)_320px] ' +
  '@min-[1100px]:grid-cols-[minmax(0,1fr)_340px] ' +
  '@min-[1400px]:grid-cols-[minmax(0,1fr)_360px] ' +
  '@min-[1760px]:grid-cols-[minmax(0,1fr)_400px] ' +
  '@min-[2200px]:grid-cols-[minmax(0,1fr)_440px]'

/** 正在就地预览的文件（null = 未展开）。诉讼页的 PickedFile 是它的超集（多带 kind/ownerId） */
export interface PickedFile {
  subpath: string
  name: string
  size?: number
  modified_at?: string
  mtime?: number
}

/**
 * 就地编辑的三种布局（54 号原型「点交付物在当前页展开 OnlyOffice」）：
 *
 * | 形态 | 条件 | 布局 |
 * |---|---|---|
 * | ① 未展开 | `picked == null` | 左内容 + 右档案卡 |
 * | ② 文档在右 | 展开 + 净宽 ≥1100 | 左内容（档案卡退到内容列底部）+ 右文档，可拖宽 |
 * | ③ 文档通栏 | 其余（净宽不足 / 沉浸态） | 文档占满整宽置顶，内容与档案卡排到其下 |
 *
 * ③ 的两个来由合并成一种排法：净宽不足时与其把 A4 挤进 500px，不如独占一行；
 * 而「沉浸编辑」就是「占满整宽 + 一屏高 + 不吸顶」，与前者只差高度策略。
 * 之前是分开的两态（含一个「宽度不够就不置顶」的门槛），结果是同一个页面
 * 要维护两种相似的叠法，还容易在某一路径上把文档排到内容后面去。
 *
 * **为什么门槛用「净宽」而不是容器查询**：助手是 fixed 抽屉，容器测不到它；宽屏
 * 下助手恒并排让位，主区会被压掉数百像素（见 use-net-width）。第 ③ 态下文档紧贴
 * 助手——律师此刻的注意力就是「左看文档右问 AI」，内容沉底滚动可达。
 *
 * **文档栏为什么不做成弹层（④ 用布局而不是 fixed 遮罩）**：页面 `<main>` 带
 * `app-page-enter` 进场动画（transform: translateY(0) + fill-mode both），
 * 祖先只要带 transform 就是 fixed 的包含块，`inset-0` 会变成「整页高」而不是
 * 「视口高」，遮罩反而错位；而 portal 到 body 会让画布换父节点、编辑器重挂。
 *
 * **文档列永远挂在容器末尾、靠 `order-first` 排到最前**：OnlyOffice 画布一旦换
 * DOM 父节点就会整份重开（DS 实例销毁重建，未保存的编辑直接没了）。所以 ②③④
 * 三态共用**同一棵 DOM**，只换类名与宽度，绝不把文档卡挪到别的兄弟位置。
 * 同理分隔条常驻、只用 `hidden` 隐显，不参与「兄弟节点数量」的变化。
 *
 * 文档栏可拖拽调宽并记住偏好：只有档案卡时 360px 够用，装 OnlyOffice 时 A4 正文
 * 600px 以下就开始缩字，写死断点只能猜折中值。
 */
export function DealDocLayout({
  picked,
  docSideBySide,
  kind = 'contract',
  ownerId,
  widthStorageKey = 'fachuan:nonlit:preview-width',
  immersive = false,
  onToggleImmersive,
  onClose,
  onSaved,
  onReview,
  onDirtyChange,
  aside,
  rail,
  children,
}: {
  picked: PickedFile | null
  /** 净宽够不够并排（第 ② 态）；不够则由本组件自己转成 ③ */
  docSideBySide: boolean
  /** 文档归属通道：合同文件夹（contract）或案件文件夹（case） */
  kind?: FolderOwnerKind
  ownerId: number
  /** 文档栏宽度偏好的 localStorage 键（诉讼页与非诉页各记各的） */
  widthStorageKey?: string
  /** 沉浸态（④）：由页面持有，关掉文档时一并复位 */
  immersive?: boolean
  onToggleImmersive?: () => void
  onClose: () => void
  onSaved: () => void
  /** 「AI 审查」入口（只对合同文件开放，案件文件传 undefined） */
  onReview?: (f: { subpath: string; name: string }) => void
  /** 画布有无未保存改动（页面用它拦关闭/换文件，见 useDocDirtyGuard） */
  onDirtyChange?: (dirty: boolean) => void
  /** 内容列（阶段表 / 服务事项流 / 案件程序链 + 下一程序） */
  children: ReactNode
  /** 档案卡（未展开时在右栏；展开后沉到内容列底部） */
  rail: ReactNode
  /** 右栏在未预览时的额外节（专项页的阶段派生目录） */
  aside?: ReactNode
}) {
  const panel = useResizablePanel({
    storageKey: widthStorageKey,
    defaultWidth: 720,
    min: 360,
    maxRatio: 0.78,
  })
  // 解构出来用：直接把 hook 返回值对象挂在 JSX 上会被 react-hooks/refs 判成
  // 「渲染期读 ref」（它无法穿透对象判断哪些字段是 ref）
  const { containerRef, dragging, onPointerDown, setWidth, effectiveWidth } = panel

  /** 沉浸只在有文档时成立：关掉文档后残留的 true 不该把下一份也直接铺满 */
  const docImmersive = Boolean(picked) && immersive
  /** ② 文档在右（可拖宽） */
  const docBeside = Boolean(picked) && docSideBySide && !docImmersive
  /** ③④ 文档置顶通栏：同一棵 DOM，只换高度策略（③ 吸顶，④ 不吸顶以免压住下方内容） */
  const docOnTop = Boolean(picked) && !docBeside

  const doc = picked && (
    <div
      className={cn(
        'flex flex-col',
        'h-[calc(100vh-100px)] min-h-[520px]',
        // ③ 吸顶：内容沉到文档下面，滚动时文档仍在眼前
        // ④ 不吸顶：沉浸态文档就占一屏，再吸顶会把「想看一眼案件链」变成不可达
        docImmersive ? '' : 'sticky top-[70px]',
      )}
    >
      <FilePreviewCard
        kind={kind}
        ownerId={ownerId}
        file={picked}
        onClose={onClose}
        onSaved={onSaved}
        onReview={onReview}
        immersive={docImmersive}
        onToggleImmersive={onToggleImmersive}
        onDirtyChange={onDirtyChange}
      />
    </div>
  )

  return (
    <div
      ref={containerRef}
      className={
        !picked
          ? COLUMNS_CLS
          : docBeside
            ? 'flex items-start gap-[8px]'
            : 'flex flex-col gap-[18px]'
      }
    >
      {/* 内容列：永远第 1 个孩子。展开文档后档案卡沉到它底部——档案是「对照用」
          的事实条，不该和文档抢横向空间（此前档案卡被整列拉宽到 720–780px，
          期限/当事人被摊成一排空行，就是这个布局的锅）。 */}
      <div className={cn('min-w-0 space-y-[18px]', docBeside && 'flex-1')}>
        {children}
        {picked && rail}
      </div>

      {/* 分隔条：常驻、用 className 隐显（见头部注释：不改变兄弟节点数量） */}
      <ResizeHandle
        className={docBeside ? undefined : 'hidden'}
        dragging={dragging}
        onPointerDown={onPointerDown}
        onKeyAdjust={(dir) => setWidth((w) => Math.max(320, w + dir * 40))}
        label="调整预览栏宽度"
      />

      {picked ? (
        <div
          className={cn('min-w-0', docOnTop && 'order-first w-full')}
          style={docBeside && effectiveWidth ? { width: effectiveWidth, flex: 'none' } : undefined}
        >
          {doc}
        </div>
      ) : (
        <div className="min-w-0 space-y-[18px]">
          {aside}
          {rail}
        </div>
      )}
    </div>
  )
}
