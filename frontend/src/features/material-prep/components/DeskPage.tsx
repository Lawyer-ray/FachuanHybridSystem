import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageFade } from '@/components/shared/PageFade'
import { useMaterialPacks, useCreatePack, useJudgePack, useDeletePack } from '../hooks/use-inbox'
import { useReader } from '../store'
import { useDeskKeyboard } from '../hooks/use-desk-keyboard'
import { useDeskRing } from '../hooks/use-desk-ring'
import { useDeskRouteSync } from '../hooks/use-desk-route-sync'
import { DeskTabs } from './DeskTabs'
import { PackGrid } from './PackGrid'
import { DeskDropLayer } from './DeskDropLayer'
import { DeskDialogs } from './DeskDialogs'
import { Reader } from './reader/Reader'
import type { InboxMessage, PackStatus } from '../types'
import '../material-prep.css'

type Tab = PackStatus

/**
 * 材料预处理工作台（DeskPage）：只做顶层状态与编排——
 * 拖拽上传、页签过滤/计数、卡片离场动画、弹窗开关，
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

  const [tab, setTab] = useState<Tab>('todo')
  const [sel, setSel] = useState(0)
  const [leaving, setLeaving] = useState<Record<number, 'left' | 'right'>>({})
  const [assigning, setAssigning] = useState<InboxMessage | null>(null)
  // 待确认删除的材料包（破坏性操作，右键后先经 AlertDialog 确认）
  const [deleteTarget, setDeleteTarget] = useState<InboxMessage | null>(null)
  // 待重命名的材料包（右键菜单打开），null 时关闭
  const [renameTarget, setRenameTarget] = useState<InboxMessage | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const ringRef = useRef<HTMLDivElement>(null)
  const dragDepth = useRef(0)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

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

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      setUploading(true)
      try {
        await createPack.mutateAsync(Array.from(files))
        setTab('todo')
        setSel(0)
        toast.success(`已收进 ${files.length} 份材料`)
      } catch {
        toast.error('上传失败，请检查后端连接')
      } finally {
        setUploading(false)
        setDragging(false)
      }
    },
    [createPack],
  )

  const onPickFiles = useCallback(() => fileInputRef.current?.click(), [])

  // 离场动画后移除 leaving 标记（并把卡片从当前列表刷走）
  const judge = useCallback(
    async (pack: { id: number }, target: 'done' | 'filed') => {
      if (leaving[pack.id]) return
      setLeaving((prev) => ({ ...prev, [pack.id]: target === 'done' ? 'right' : 'left' }))
      try {
        await judgePack.mutateAsync({ id: pack.id, status: target })
        toast(target === 'done' ? '已归案' : '已归档留痕，未建案')
      } catch {
        toast.error('状态更新失败，请重试')
      }
      setTimeout(() => {
        setLeaving((prev) => {
          const n = { ...prev }
          delete n[pack.id]
          return n
        })
      }, 540)
    },
    [judgePack, leaving],
  )

  const openAt = useCallback(
    (index: number) => {
      const p = visible[index]
      if (p) {
        openPack(p.id)
        navigate(`/material-prep/${p.id}`)
      }
    },
    [visible, openPack, navigate],
  )

  useDeskKeyboard({ visible, openId, sel, setSel, openAt, judge })
  useDeskRing({ sel, dep: [visible, tab] as unknown, gridRef, wrapRef, ringRef })

  const confirmDelete = useCallback(() => {
    const p = deleteTarget
    if (!p) return
    deletePack
      .mutateAsync(p.id)
      .then(() => {
        toast(`${p.subject} 已删除`)
        setDeleteTarget(null)
      })
      .catch(() => toast.error('删除失败，请重试'))
  }, [deleteTarget, deletePack])

  return (
    <div
      className="relative min-h-screen bg-background"
      onDragEnter={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        dragDepth.current += 1
        setDragging(true)
      }}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'copy'
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
        handleFiles(e.dataTransfer.files)
      }}
    >
      {/* 顶部导航：与首页共用同一套（components/shared/AppNavbar） */}
      {/* 退出登录由 AppNavbar 内部统一处理（含确认弹窗与跳转），这里只接提示 */}
      <AppNavbar onNotify={(m) => toast.info(m)} />

      {/* 内容区包一层入场过渡：navbar 不变，只有下面这部分播动画 */}
      <PageFade>
        <main className="relative px-7 pb-24 pt-6">
          <DeskTabs
            tab={tab}
            setTab={(t) => {
              setTab(t)
              setSel(0)
            }}
            counts={counts}
            uploading={uploading}
            onPickFiles={onPickFiles}
          />

          {isLoading ? (
            <div className="flex items-center gap-2 py-20 text-sm text-secondary-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> 加载材料包…
            </div>
          ) : error ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-6 text-sm text-destructive">
              无法加载材料包：{error instanceof Error ? error.message : '未知错误'}
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
              onReject={(p) => judge(p, 'filed')}
              onAccept={setAssigning}
              onRename={setRenameTarget}
              onDelete={setDeleteTarget}
              onPickFiles={onPickFiles}
            />
          )}
        </main>
      </PageFade>

      <DeskDropLayer dragging={dragging} fileInputRef={fileInputRef} onFiles={handleFiles} />

      {openId != null && <Reader />}

      <DeskDialogs
        assigning={assigning}
        onAssignCancel={() => setAssigning(null)}
        onAssignConfirm={(p) => {
          setAssigning(null)
          judge(p, 'done')
        }}
        deleteTarget={deleteTarget}
        onDeleteCancel={() => setDeleteTarget(null)}
        onDeleteConfirm={confirmDelete}
        deleting={deletePack.isPending}
        renameTarget={renameTarget}
        onRenameOpenChange={() => setRenameTarget(null)}
      />
    </div>
  )
}
