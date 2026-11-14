import { useCallback, useMemo, useRef } from 'react'
import { materialPrepDetail } from '@/app/paths'
import { useNavigate, useParams } from 'react-router'
import { useMaterialPacks } from '../hooks/use-inbox'
import { useReader } from '../store'
import { isPackStage, stageToQuery } from '../stages'
import { useDeskKeyboard } from '../hooks/use-desk-keyboard'
import { useDeskRing } from '../hooks/use-desk-ring'
import { useDeskRouteSync } from '../hooks/use-desk-route-sync'
import { DeskTabs } from './DeskTabs'
import { DeskToolbar } from './DeskToolbar'
import { DESK_SURFACE_CLASS, toolbarSlotsFor } from './desk-toolbar-types'
import { DeskDropLayer } from './DeskDropLayer'
import { Reader } from './reader/Reader'
import { ReaderLoading } from './reader/ReaderChrome'
import { useInboxCounts } from '../inbox/hooks/use-inbox'
import type { InboxMessage, PackStatus } from '../types'
import { useDeskFilters } from './use-desk-filters'
import { useDeskDialogs } from './use-desk-dialogs'
import { useDeskUpload } from './use-desk-upload'
import { useDeskJudge } from './use-desk-judge'
import { DeskMainArea } from './DeskMainArea'
import { DeskDialogHost } from './DeskDialogHost'
import "../material-prep.css"

type Tab = PackStatus

/**
 * 预处理工作台（DeskPage）：整条漏斗的**唯一页面**。
 *
 * 一级阶段页签 `收件箱 → 待处理 → 已归案 → 不接归档` 就是流水线顺序，
 * 收件箱与材料包同页——它们是前后两段而非平级入口（见 stages.ts 的说明）。
 *
 * 本组件只做顶层编排：把四处状态簇的 hook 接到一起，决定工具栏槽位与主区域
 * 展示哪一块。状态簇各自归口——
 *   · `useDeskFilters`  阶段 / 页签 / 选中项 / 工具栏筛选 / 列表-卡片形态
 *   · `useDeskDialogs`  四个浮层的开关与目标对象
 *   · `useDeskUpload`   建包动作与拖放/上传中的 UI 态
 *   · `useDeskJudge`    归案 / 归档 / 删除动作与卡片离场标记
 * 具体的网格 / 页签 / 弹窗 / 拖放层各自下沉到子组件，副作用收敛到 hooks。
 */
export function DeskPage() {
  const navigate = useNavigate()
  // 路由里的 :id。刷新 / 直达 / 前进后退时它比 store 里的 openId **先就位**：
  // openId 要等 useDeskRouteSync 的 effect 异步打开才变。
  const { id: routeId } = useParams()
  const { data: packs, isLoading, error } = useMaterialPacks()
  const openPack = useReader((s) => s.open)
  const openId = useReader((s) => s.openId)

  const {
    stage,
    tab,
    setStage,
    sel,
    setSel,
    source,
    setSource,
    search,
    setSearch,
    unreadOnly,
    setUnreadOnly,
    unreadCount,
    viewMode,
    setViewMode,
  } = useDeskFilters()

  const {
    assigning,
    setAssigning,
    closeAssign,
    deleteTarget,
    setDeleteTarget,
    closeDelete,
    renameTarget,
    setRenameTarget,
    closeRename,
    shareLinksOpen,
    setShareLinksOpen,
  } = useDeskDialogs()

  // 上传成功后落到「待处理」并清空选中项（新包落在那里）
  const onPackCreated = useCallback(() => {
    setStage('todo')
    setSel(0)
  }, [setStage, setSel])

  const {
    fileInputRef,
    dragging,
    uploading,
    handleFiles,
    onPickFiles,
    onDragEnter,
    onDragLeave,
    onDrop,
  } = useDeskUpload({ onCreated: onPackCreated })

  const { leaving, judge, judgeVoid, rejectPack, confirmDelete, deleting } =
    useDeskJudge({ deleteTarget, onDeleted: closeDelete })

  const gridRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const ringRef = useRef<HTMLDivElement>(null)

  useDeskRouteSync()

  // 按页签过滤，正在离场的卡片留在本轮内做动画（但仍按原状态归属其所在分页列表）
  const visible = useMemo(() => {
    const byTab = (packs || []).filter((p) => p.status === tab)
    return byTab.filter((p) => !leaving[p.id])
  }, [packs, tab, leaving])

  const counts = useMemo(() => {
    const c: Record<Tab, number> = { todo: 0, done: 0, filed: 0 }
    ;(packs || []).forEach((p) => {
      c[p.status] = (c[p.status] || 0) + 1
    })
    return c
  }, [packs])

  // 收件箱角标：一级页签上要能和眼前这批消息对上，故复用收件箱列表的取数口径
  const inboxCount = useInboxCounts()
  const stageCounts = useMemo(
    () => ({
      inbox: inboxCount,
      todo: counts.todo,
      done: counts.done,
      filed: counts.filed,
    }),
    [inboxCount, counts],
  )

  const openAt = useCallback(
    (index: number) => {
      const p = visible[index]
      if (!p) return
      void openPack(p.id)
      // 跳详情时必须带上当前 stage。
      //
      // 不带会怎样：详情路由（/material-prep/571）没有 ?stage=，DeskPage 里
      // parseStage(null) 回落成「收件箱」——于是这一帧主区域渲染的是收件箱列表、
      // 页签也跳到收件箱，紧接着阅读器才盖上来。用户看到的就是
      // 「闪一下列表再进详情」。
      //
      // 用当前 location 的 stage 而不是写死 tab：从「已归案」点开的包，退出时
      // 也该回「已归案」。
      const q = stageToQuery(isPackStage(stage) ? stage : tab)
      void navigate(`${materialPrepDetail(p.id)}${q ? `?stage=${q}` : ''}`)
    },
    [visible, openPack, navigate, stage, tab],
  )

  useDeskKeyboard({
    visible,
    openId,
    sel,
    setSel,
    openAt,
    judge: judgeVoid,
    gridRef,
  })
  useDeskRing({ sel, visible, tab, gridRef, wrapRef, ringRef })

  /**
   * 是否处于「详情意图」：URL 带 :id，或 store 已打开。
   *
   * 为什么不能只看 openId：刷新 / 直达 / 前进后退时，URL 里的 :id 是**首帧就有**的，
   * 而 openId 要等 useDeskRouteSync 的 effect 异步打开才变。只判 openId 的话，
   * 首帧会把列表完整渲染一遍，紧接着阅读器盖上来——用户看到的就是
   * 「先闪一下列表页再进详情」。
   *
   * 同理不能只看 routeId：关闭阅读器时 navigate 是异步的，那一瞬 routeId 仍在，
   * 得靠 openId 的清除来立即反馈。两者取或，两头都不闪。
   */
  const detailIntent = routeId != null || openId != null

  return (
    // 最小高度撑满导航栏以下的整个视口（--app-navbar-h 与 AppNavbar 同源）：
    // 列表再短，把文件拖到下方空白处也能命中拖放层
    <div
      className="relative min-h-[calc(100dvh-var(--app-navbar-h))]"
      onDragEnter={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        onDragEnter()
      }}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        e.dataTransfer.dropEffect = "copy"
      }}
      onDragLeave={onDragLeave}
      onDrop={(e) => {
        e.preventDefault()
        onDrop(e.dataTransfer.files)
      }}
    >
      {/* 导航栏由 AppShell 常驻；入场过渡挂在 main 上——换页才重挂播一次，
          列表 ↔ 详情（/material-prep/:id）同一实例不重播，阅读器淡入不被叠加 */}
      <main className="app-page-enter relative flex min-h-[calc(100dvh-var(--app-navbar-h)-6rem)] flex-col px-7 pb-24 pt-6">
        {/* 详情意图下**整块列表不渲染**（不是视觉隐藏）：
            · 避免刷新时先闪一帧列表；
            · 少跑一遍 packs 列表的派生计算与大列表渲染；
            · 阅读器是 FixedReader 覆盖层，列表留在下面只会白白参与布局。
            条件渲染比 display:none 更彻底：连 hooks 之外的子组件树都不挂载。 */}
        {!detailIntent && (
          <>
        <DeskTabs
          stage={stage}
          setStage={setStage}
          counts={stageCounts}
          uploading={uploading}
          onPickFiles={onPickFiles}
          onOpenShareLinks={() => setShareLinksOpen(true)}
        />

        {/* 统一工具栏：阶段切换时它不重挂（在 key={stage} 那层之外），只有槽位变化，
            这样切页签时是「同一条工具栏换了控件」而不是「换了个页面」。 */}
        {/* 工具栏与主区域共用**同一个**卡片容器：工具栏是这张卡的表头（自带 border-b），
            主区域是卡身。以前这里各自套一层 DESK_SURFACE_CLASS，页面上会出现
            「两张上下叠放的独立卡片」，反而比统一前更分裂。 */}
        <div data-testid="desk-surface" className={DESK_SURFACE_CLASS}>
          <DeskToolbar
            stage={stage}
            slots={toolbarSlotsFor(stage)}
            handlers={{
              source,
              onSourceChange: setSource,
              unreadOnly,
              onUnreadOnlyChange: setUnreadOnly,
              unreadCount,
              search,
              onSearchChange: setSearch,
              viewMode,
              onViewModeChange: setViewMode,
            }}
          />

          <DeskMainArea
            stage={stage}
            tab={tab}
            viewMode={viewMode}
            source={source}
            onSourceChange={setSource}
            search={search}
            onSearchChange={setSearch}
            unreadOnly={unreadOnly}
            onUnreadOnlyChange={setUnreadOnly}
            isLoading={isLoading}
            error={error}
            visible={visible}
            leaving={leaving}
            gridRef={gridRef}
            wrapRef={wrapRef}
            ringRef={ringRef}
            onOpen={openAt}
            onReject={rejectPack}
            onAccept={setAssigning}
            onRename={setRenameTarget}
            onDelete={setDeleteTarget}
          />
        </div>
          </>
        )}
      </main>

      <DeskDropLayer
        dragging={dragging}
        fileInputRef={fileInputRef}
        onFiles={(fs) => {
          void handleFiles(fs)
        }}
      />

      {/* 详情意图但阅读器尚未就绪：显示与 ReaderLoading 同形的占位，
          而不是留一片空白。与 openId 分支共用同一层，避免两个转圈叠在一起。 */}
      {openId != null ? <Reader /> : detailIntent ? <ReaderLoading /> : null}

      <DeskDialogHost
        assigning={assigning}
        onAssignCancel={closeAssign}
        onAssignConfirm={(p: InboxMessage) => {
          closeAssign()
          void judge(p, 'done')
        }}
        deleteTarget={deleteTarget}
        onDeleteCancel={closeDelete}
        onDeleteConfirm={confirmDelete}
        deleting={deleting}
        renameTarget={renameTarget}
        onRenameClose={closeRename}
        shareLinksOpen={shareLinksOpen}
        onShareLinksOpenChange={setShareLinksOpen}
      />
    </div>
  )
}
