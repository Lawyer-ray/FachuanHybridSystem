import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { materialPrepDetail } from '@/app/paths'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import {
  useMaterialPacks,
  useCreatePack,
  useJudgePack,
  useDeletePack,
} from '../hooks/use-inbox'
import { useReader } from '../store'
import {
  PACK_LEAVE_REMOVAL_MS,
  formatMB,
  uploadSizeCapBytes,
} from '../constants'
import { isPackStage, parseStage, type PrepStage } from '../stages'
import { useDeskKeyboard } from '../hooks/use-desk-keyboard'
import { useDeskRing } from '../hooks/use-desk-ring'
import { useDeskRouteSync } from '../hooks/use-desk-route-sync'
import { DeskTabs } from './DeskTabs'
import { DeskToolbar } from './DeskToolbar'
import {
  DESK_SURFACE_CLASS,
  STAGE_DEFAULT_VIEW,
  toolbarSlotsFor,
} from './desk-toolbar-types'
import type { DeskViewMode } from './desk-toolbar-types'
import { PackGrid } from './PackGrid'
import { DeskDropLayer } from './DeskDropLayer'
import { DeskDialogs } from './DeskDialogs'
import { ShareLinkPanel } from './ShareLinkPanel'
import { Reader } from './reader/Reader'
import { InboxView } from '../inbox'
import { useInboxCounts, useInboxList } from '../inbox/hooks/use-inbox'
import { countUnread } from '../inbox/domain'
import type { InboxSourceFilter } from '../inbox/types'
import type { InboxMessage, PackStatus } from '../types'
import "../material-prep.css"

type Tab = PackStatus

/**
 * 预处理工作台（DeskPage）：整条漏斗的**唯一页面**。
 *
 * 一级阶段页签 `收件箱 → 待处理 → 已归案 → 不接归档` 就是流水线顺序，
 * 收件箱与材料包同页——它们是前后两段而非平级入口（见 stages.ts 的说明）。
 *
 * 本组件只做顶层状态与编排——阶段切换、拖拽上传、卡片离场动画、弹窗开关，
 * 具体的网格 / 页签 / 弹窗 / 拖放层各自下沉到子组件，副作用收敛到 hooks。
 */
export function DeskPage() {
  const navigate = useNavigate()
  const { data: packs, isLoading, error } = useMaterialPacks()
  const createPack = useCreatePack()
  const judgePack = useJudgePack()
  const deletePack = useDeletePack()
  const openPack = useReader((s) => s.open)
  const openId = useReader((s) => s.openId)

  // 阶段入 URL（?stage=todo）：可刷新、可分享、可前进后退。收件箱里的
  // 「转材料包」闭环也靠它跳到待处理，而不是另写一套页内状态。
  const [params, setParams] = useSearchParams()
  const stage = parseStage(params.get('stage'))
  // 材料包三态页签的当前值（收件箱阶段下沿用上一次的三态，供 PackGrid/键盘导航用）
  const [packTab, setPackTab] = useState<Tab>('todo')
  const tab: Tab = isPackStage(stage) ? stage : packTab

  const [sel, setSel] = useState(0)

  // ── 统一工具栏的筛选状态 ──────────────────────────────────
  // 收件箱的筛选以前是 InboxView 内部的本地 state，工具栏上提到本组件后
  // 必须跟着上提：工具栏与列表主体是兄弟节点，状态留在下面就会出现
  // 「点了药丸但列表不动」。InboxView 现在是受控组件，只认这里的值。
  const [source, setSource] = useState<InboxSourceFilter>('all')
  const [search, setSearch] = useState("")
  const [unreadOnly, setUnreadOnly] = useState(false)

  // 「未读」药丸上的数字：**当前来源档位 + 搜索词下的未读条数**，与未读开关无关。
  //
  // 关键：这里**不传 `unreadOnly`**。它是发给后端的查询参数（unread_only=true），
  // 传了就会只拿回未读行，数字被自己的开关坍缩——开关一翻，数字跟着抖甚至自指。
  // 语义上两者本就不同：「要不要只看未读」是筛选意图，「这里有多少未读」是事实。
  //
  // 另：不能对全库另发请求——顶栏那个数要和眼前这批消息对得上。
  const inboxRows = useInboxList({ source, search })
  const unreadCount = useMemo(
    () => countUnread(inboxRows.data ?? []),
    [inboxRows.data],
  )

  // 「列表 / 卡片」按阶段分别记住用户的切换结果：从「待处理」切到「已归案」
  // 再切回来，待处理仍然是他上次选的那种排布。只在内存里，不持久化——
  // 刷新后回到 STAGE_DEFAULT_VIEW 的缺省（消息流用列表、材料包用卡片）。
  const [viewModes, setViewModes] = useState<
    Partial<Record<PrepStage, DeskViewMode>>
  >({})
  const viewMode: DeskViewMode = viewModes[stage] ?? STAGE_DEFAULT_VIEW[stage]
  const setViewMode = useCallback(
    (m: DeskViewMode) => setViewModes((prev) => ({ ...prev, [stage]: m })),
    [stage],
  )

  const setStage = useCallback(
    (s: PrepStage) => {
      if (isPackStage(s)) setPackTab(s)
      setSel(0)
      // 只在**现有参数上**改 stage，不整体替换。
      // setParams 传对象是覆盖语义：以前直接 setParams({stage:s}) 会把
      // 深链接的 ?message=<id> 一起抹掉（收件箱打开某条消息的直达能力失效）。
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          // 收件箱是默认阶段：不往 URL 里写冗余参数，保持 /material-prep 干净
          if (s === 'inbox') next.delete('stage')
          else next.set('stage', s)
          return next
        },
        { replace: true },
      )
    },
    [setParams, setPackTab, setSel],
  )

  const [leaving, setLeaving] = useState<Record<number, "left" | "right">>({})
  const [assigning, setAssigning] = useState<InboxMessage | null>(null)
  // 待确认删除的材料包（破坏性操作，右键后先经 AlertDialog 确认）
  const [deleteTarget, setDeleteTarget] = useState<InboxMessage | null>(null)
  // 待重命名的材料包（右键菜单打开），null 时关闭
  const [renameTarget, setRenameTarget] = useState<InboxMessage | null>(null)
  // 客户上传链接管理面板
  const [shareLinksOpen, setShareLinksOpen] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const ringRef = useRef<HTMLDivElement>(null)
  const dragDepth = useRef(0)
  const leaveTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set())
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

  useDeskRouteSync()

  // 卸载时清掉所有离场清理定时器，避免卸载后仍 setState
  useEffect(() => {
    const timers = leaveTimersRef.current
    return () => {
      timers.forEach((t) => window.clearTimeout(t))
      timers.clear()
    }
  }, [])

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
  const stageCounts = useMemo<Record<PrepStage, number>>(
    () => ({
      inbox: inboxCount,
      todo: counts.todo,
      done: counts.done,
      filed: counts.filed,
    }),
    [inboxCount, counts],
  )

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      const list = Array.from(files)
      // 体积预检：后端对单文件有硬上限（普通 50MB / 压缩包 200MB），超限必被
      // 400 拒绝。传到一半才被拒既浪费上行带宽又让用户白等，这里提前报。
      // 逐个提示第一个超限文件即可——一次拖 10 个超限文件时堆 10 条 toast
      // 只会把提示区刷满，反而看不到具体哪个文件有问题。
      const oversized = list.find((f) => f.size > uploadSizeCapBytes(f.name))
      if (oversized) {
        toast.error(
          `${oversized.name} 过大（${formatMB(oversized.size)}），单个不能超过 ${formatMB(uploadSizeCapBytes(oversized.name))}`,
        )
        setDragging(false)
        return
      }
      setUploading(true)
      try {
        const detail = await createPack.mutateAsync(list)
        setStage('todo')
        setSel(0)
        // 压缩包会被服务端展开：以响应里的实际附件数为准，别拿输入文件数冒充
        const total = detail?.attachment_count ?? list.length
        const hadArchive = list.some((f) => /\.(zip|rar|7z)$/i.test(f.name))
        toast.success(
          hadArchive
            ? `压缩包已展开，共收进 ${total} 份材料`
            : `已收进 ${total} 份材料`,
        )
      } catch (e) {
        // 必须透出后端文案：上传失败的一大类是「附件过大 / 格式不支持」这类
        // 可自行处理的 400，后端 message 已经写得很具体。以前这里吞掉错误
        // 一律弹「请检查后端连接」，会让 65MB 的 PDF 被拒时用户以为后端挂了
        // （实测：一份 65.7MB / 164 页的扫描件超 50MB 上限被拒，看到的却是连接问题）。
        toast.error(errMessage(e, "上传失败，请重试"))
      } finally {
        setUploading(false)
        setDragging(false)
      }
    },
    [createPack, setStage],
  )

  const onPickFiles = useCallback(() => fileInputRef.current?.click(), [])

  // 离场动画后移除 leaving 标记（并把卡片从当前列表刷走）
  const judge = useCallback(
    async (pack: { id: number }, target: "done" | 'filed') => {
      if (leaving[pack.id]) return
      setLeaving((prev) => ({
        ...prev,
        [pack.id]: target === "done" ? "right" : 'left',
      }))
      try {
        await judgePack.mutateAsync({ id: pack.id, status: target })
        toast(target === "done" ? "已归案" : "已归档留痕，未建案")
      } catch (e) {
        toast.error(errMessage(e, "状态更新失败，请重试"))
      }
      const t = setTimeout(() => {
        leaveTimersRef.current.delete(t)
        setLeaving((prev) => {
          const n = { ...prev }
          delete n[pack.id]
          return n
        })
      }, PACK_LEAVE_REMOVAL_MS)
      leaveTimersRef.current.add(t)
    },
    [judgePack, leaving],
  )

  // judge 是 async（返回 Promise）；键盘导航 / 弹窗回调期望 void 返回，
  // 统一包一层 fire-and-forget（内部 busy/leaving 守卫防重入，无需等待结果）
  const judgeVoid = useCallback(
    (pack: { id: number }, target: "done" | 'filed') => {
      void judge(pack, target)
    },
    [judge],
  )

  const openAt = useCallback(
    (index: number) => {
      const p = visible[index]
      if (p) {
        void openPack(p.id)
        void navigate(materialPrepDetail(p.id))
      }
    },
    [visible, openPack, navigate],
  )

  // 「不接」回调稳定化：内联箭头会透传到 PackCard 打穿 memo
  const rejectPack = useCallback(
    (p: InboxMessage) => {
      void judge(p, 'filed')
    },
    [judge],
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

  const confirmDelete = useCallback(() => {
    const p = deleteTarget
    if (!p) return
    deletePack
      .mutateAsync(p.id)
      .then(() => {
        toast(`${p.subject} 已删除`)
        setDeleteTarget(null)
      })
      .catch((e) => toast.error(errMessage(e, "删除失败，请重试")))
  }, [deleteTarget, deletePack])

  return (
    // 最小高度撑满导航栏以下的整个视口（--app-navbar-h 与 AppNavbar 同源）：
    // 列表再短，把文件拖到下方空白处也能命中拖放层
    <div
      className="relative min-h-[calc(100dvh-var(--app-navbar-h))]"
      onDragEnter={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        dragDepth.current += 1
        setDragging(true)
      }}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        e.dataTransfer.dropEffect = "copy"
      }}
      onDragLeave={() => {
        dragDepth.current -= 1
        if (dragDepth.current <= 0) {
          dragDepth.current = 0
          setDragging(false)
        }
      }}
      onDrop={(e) => {
        e.preventDefault()
        dragDepth.current = 0
        void handleFiles(e.dataTransfer.files)
      }}
    >
      {/* 导航栏由 AppShell 常驻；入场过渡挂在 main 上——换页才重挂播一次，
          列表 ↔ 详情（/material-prep/:id）同一实例不重播，阅读器淡入不被叠加 */}
      <main className="app-page-enter relative flex min-h-[calc(100dvh-var(--app-navbar-h)-6rem)] flex-col px-7 pb-24 pt-6">
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

          {/* 阶段切换的淡入：key={stage} 确保换阶段时这层重挂，
              app-stage-enter 才会重新播一次。不加 key 时 React 复用同一节点，
              过渡不会触发，表现为主区域内容硬切（2026-11-04 反馈「切换不自然」）。
              只给主区域而不给整页：页签不该跟着一起淡，它应该保持常驻。
              注意它**在卡片容器内部**：工具栏是卡的表头、这块是卡身，
              两者必须同属一张卡，否则页面上会出现两张上下叠放的黑框。 */}
          <div
            key={stage}
            className="app-stage-enter flex min-h-0 flex-1 flex-col overflow-y-auto"
          >
            {!isPackStage(stage) ? (
              /* 收件箱阶段：主区域交给 InboxView（受控：筛选值来自本组件的工具栏）。
               拖放层仍在外层生效——把文件拖进收件箱页时照旧建包并跳到「待处理」。 */

              <InboxView
                source={source}
                onSourceChange={setSource}
                search={search}
                onSearchChange={setSearch}
                unreadOnly={unreadOnly}
                onUnreadOnlyChange={setUnreadOnly}
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
             fallback 取「未知错误」——旧实现就在 message 缺失时显示它，
             不改文案。 */
              <div className="space-y-1.5 p-4">
                <p className="text-sm text-destructive">无法加载材料包：</p>
                <ErrorBlock
                  error={error}
                  fallback="未知错误"
                  className="px-4 py-6 text-sm"
                />
              </div>
            ) : (
              <PackGrid
                gridRef={gridRef}
                wrapRef={wrapRef}
                ringRef={ringRef}
                packs={visible}
                tab={tab}
                leaving={leaving}
                onOpen={openAt}
                onReject={rejectPack}
                onAccept={setAssigning}
                onRename={setRenameTarget}
                onDelete={setDeleteTarget}
                viewMode={viewMode}
              />
            )}
          </div>
        </div>
      </main>

      <DeskDropLayer
        dragging={dragging}
        fileInputRef={fileInputRef}
        onFiles={(fs) => {
          void handleFiles(fs)
        }}
      />

      {openId != null && <Reader />}

      <DeskDialogs
        assigning={assigning}
        onAssignCancel={() => setAssigning(null)}
        onAssignConfirm={(p) => {
          setAssigning(null)
          void judge(p, 'done')
        }}
        deleteTarget={deleteTarget}
        onDeleteCancel={() => setDeleteTarget(null)}
        onDeleteConfirm={confirmDelete}
        deleting={deletePack.isPending}
        renameTarget={renameTarget}
        onRenameOpenChange={() => setRenameTarget(null)}
      />

      <ShareLinkPanel open={shareLinksOpen} onOpenChange={setShareLinksOpen} />
    </div>
  )
}
