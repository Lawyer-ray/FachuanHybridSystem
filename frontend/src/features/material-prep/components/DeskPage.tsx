import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { FolderOpen, Loader2, PackagePlus, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageFade } from '@/components/shared/PageFade'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { useMaterialPacks, useCreatePack, useJudgePack, useDeletePack } from '../hooks/use-inbox'
import { useReader } from '../store'
import { PackCard } from './PackCard'
import { RenamePackDialog } from './RenamePackDialog'
import { Reader } from './reader/Reader'
import { AssignModal } from './reader/AssignModal'
import { cn } from '@/lib/utils'
import '../material-prep.css'
import type { AssignInfo, InboxMessage, PackStatus } from '../types'

type Tab = PackStatus

const TABS: { key: Tab; label: string }[] = [
  { key: 'todo', label: '待处理' },
  { key: 'done', label: '已归案' },
  { key: 'filed', label: '不接归档' },
]

export function DeskPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const { data: packs, isLoading, error } = useMaterialPacks()
  const createPack = useCreatePack()
  const judgePack = useJudgePack()
  const deletePack = useDeletePack()
  const openPack = useReader((s) => s.open)
  const openId = useReader((s) => s.openId)
  // 记录是否曾打开过详情：从打开态退到未打开时（关阅读器）回退到列表 URL
  const wasOpenRef = useRef(false)

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

  // 离场动画后移除 leaving 标记（并把卡片从当前列表刷走）
  const judge = useCallback(
    async (pack: { id: number }, target: 'done' | 'filed') => {
      if (leaving[pack.id]) return
      setLeaving((prev) => ({ ...prev, [pack.id]: target === 'done' ? 'right' : 'left' }))
      const dir = target === 'done' ? 'right' : 'left'
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
      void dir
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

  // 详情路由：路径里带 :id 时自动打开对应材料包（刷新 / 前进后退 / 分享直达）
  useEffect(() => {
    if (id == null) return
    if (useReader.getState().openId === Number(id)) return
    openPack(Number(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // 关阅读器：从打开态回退到列表 URL，避免 URL 停留在 :id
  useEffect(() => {
    const open = openId != null
    if (wasOpenRef.current && !open && id != null) {
      navigate('/material-prep', { replace: true })
    }
    if (open) wasOpenRef.current = true
  }, [openId, id, navigate])

  // 键盘导航：←→ 移、↑↓ 换行、Space/Enter 打开、X 不接
  useEffect(() => {
    if (openId != null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || (e.target as HTMLElement).closest?.('input, textarea, select'))
        return
      if (visible.length === 0) return
      const cols = gridCols()
      if (e.key === 'ArrowRight') {
        setSel((s) => Math.min(visible.length - 1, s + 1))
        e.preventDefault()
      } else if (e.key === 'ArrowLeft') {
        setSel((s) => Math.max(0, s - 1))
        e.preventDefault()
      } else if (e.key === 'ArrowDown') {
        setSel((s) => Math.min(visible.length - 1, s + (cols || 1)))
        e.preventDefault()
      } else if (e.key === 'ArrowUp') {
        setSel((s) => Math.max(0, s - (cols || 1)))
        e.preventDefault()
      } else if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        openAt(sel)
      } else if (e.key === 'x' || e.key === 'X') {
        const p = visible[sel]
        if (p) judge(p, 'filed')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, openId, sel, judge])

  // ring 高亮跟随选中卡片
  useEffect(() => {
    const ring = ringRef.current
    const wrap = wrapRef.current
    const grid = gridRef.current
    if (!ring || !wrap || !grid) return
    const paint = () => {
      const cards = grid.querySelectorAll<HTMLElement>('[data-pack-idx]')
      if (!cards.length) {
        ring.classList.remove('on')
        return
      }
      const c = cards[Math.min(sel, cards.length - 1)]
      if (!c) {
        ring.classList.remove('on')
        return
      }
      const wr = wrap.getBoundingClientRect()
      const cr = c.getBoundingClientRect()
      ring.style.width = `${cr.width}px`
      ring.style.height = `${cr.height}px`
      ring.style.transform = `translate(${cr.left - wr.left}px, ${cr.top - wr.top}px)`
      ring.classList.add('on')
    }
    const raf = () => requestAnimationFrame(paint)
    raf()
    const ro = new ResizeObserver(raf)
    ro.observe(grid)
    window.addEventListener('scroll', paint, { passive: true })
    window.addEventListener('resize', paint)
    return () => {
      ro.disconnect()
      window.removeEventListener('scroll', paint)
      window.removeEventListener('resize', paint)
    }
  }, [sel, visible, tab])

  // 关闭阅读器后让列表卡片进度/状态跟上次变化
  const prevOpenId = useRef<number | null>(null)
  useEffect(() => {
    if (prevOpenId.current != null && openId == null) {
      judgePack.invalidate()
    }
    prevOpenId.current = openId
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId])

  function gridCols(): number {
    const grid = gridRef.current
    if (!grid) return 1
    const tcs = getComputedStyle(grid).gridTemplateColumns
    return tcs.split(' ').length
  }

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
      <AppNavbar
        onLogout={() => navigate('/login', { replace: true })}
        onNotify={(m) => toast.info(m)}
      />

      {/* 内容区包一层入场过渡：navbar 不变，只有下面这部分播动画 */}
      <PageFade>
        <main className="relative px-7 pb-24 pt-6">
          {/* 页签 + 快捷键提示 */}
          <div className="mb-5 flex flex-wrap items-end gap-4">
            <div className="flex items-center gap-1.5">
              <div className="flex items-center gap-0.5 rounded-[9px] bg-secondary p-[3px]">
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => {
                      setTab(t.key)
                      setSel(0)
                    }}
                    className={cn(
                      'flex items-center gap-[6px] rounded-[7px] px-[13px] py-[6px] text-[13px] transition-colors',
                      tab === t.key
                        ? 'bg-card font-medium text-foreground shadow-sm'
                        : 'text-secondary-foreground hover:text-foreground',
                    )}
                  >
                    {t.label}
                    <span className={cn('text-[11.5px] tabular-nums', tab === t.key ? 'text-secondary-foreground' : 'text-muted-foreground')}>
                      {counts[t.key]}
                    </span>
                  </button>
                ))}
              </div>
              <span className="mx-2 hidden h-[18px] w-px bg-zinc-300 sm:block" />
              <div className="hidden items-center gap-2 text-[11.5px] text-muted-foreground sm:flex">
                <kbd className="rounded border border-border bg-card px-1 py-0.5 font-sans">↑↓←→</kbd> 选择
                <kbd className="rounded border border-border bg-card px-1 py-0.5 font-sans">空格</kbd> 打开
                <kbd className="rounded border border-border bg-card px-1 py-0.5 font-sans">X</kbd> 不接
                <span className="text-zinc-300">|</span>
                全部材料都靠手划，机器不猜
              </div>
            </div>
            <div className="ml-auto">
              <Button onClick={() => fileInputRef.current?.click()} disabled={uploading} size="sm">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />}
                新建材料包
              </Button>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 py-20 text-sm text-secondary-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> 加载材料包…
            </div>
          ) : error ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-6 text-sm text-destructive">
              无法加载材料包：{error instanceof Error ? error.message : '未知错误'}
            </div>
          ) : (
            <div className="relative" ref={wrapRef}>
              <div ref={gridRef} className="grid grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-4">
                {visible.map((p, i) => (
                  <div
                    key={p.id}
                    data-pack-idx={i}
                    className={cn(leaving[p.id] === 'right' && 'leave-right', leaving[p.id] === 'left' && 'leave-left')}
                  >
                    <ContextMenu>
                      <ContextMenuTrigger className="block">
                        <PackCard
                          pack={p}
                          finished={p.segs > 0 && p.named === p.segs}
                          leaving={leaving[p.id] ?? null}
                          onOpen={() => openAt(i)}
                          onReject={() => judge(p, 'filed')}
                          onAccept={() => setAssigning(p)}
                        />
                      </ContextMenuTrigger>
                      <ContextMenuContent className="w-44">
                        <ContextMenuItem onSelect={() => openAt(i)}>
                          <FolderOpen /> 打开材料包
                        </ContextMenuItem>
                        <ContextMenuItem onSelect={() => setRenameTarget(p)}>
                          <Pencil /> 重命名材料包
                        </ContextMenuItem>
                        <ContextMenuSeparator />
                        <ContextMenuItem variant="destructive" onSelect={() => setDeleteTarget(p)}>
                          <Trash2 /> 删除材料包
                        </ContextMenuItem>
                      </ContextMenuContent>
                    </ContextMenu>
                  </div>
                ))}

                {/* 虚线槽：第二个新建入口 */}
                {tab === 'todo' && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex min-h-[280px] cursor-pointer flex-col items-center justify-center gap-2.5 rounded-[13px] border-[1.5px] border-dashed border-zinc-300 text-secondary-foreground transition-colors hover:border-zinc-400 hover:bg-card hover:text-foreground"
                  >
                    <span className="grid h-[34px] w-[34px] place-items-center rounded-[9px] bg-secondary text-secondary-foreground">
                      <Plus className="h-4 w-4" />
                    </span>
                    <span className="text-sm">
                      {visible.length === 0 ? '全部处理完了，拖入新材料，或点这里' : '拖入材料，或点这里选文件'}
                    </span>
                    <span className="text-[11.5px] text-muted-foreground">PDF · Word · 图片 · 视频，混着来都行</span>
                  </button>
                )}

                {visible.length === 0 && tab !== 'todo' && (
                  <div className="col-span-full flex flex-col items-center gap-2 rounded-[13px] border border-dashed border-zinc-300 py-16 text-sm text-secondary-foreground">
                    这里还没有{tab === 'done' ? '已归案' : '归档'}的材料包
                  </div>
                )}
              </div>
              <div ref={ringRef} className="mp-ring" />
            </div>
          )}
        </main>
      </PageFade>

      {/* 拖放遮罩 */}
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-foreground/20 backdrop-blur-[1px]">
          <div className="rounded-2xl border border-primary bg-card px-10 py-8 text-center shadow-xl">
            <p className="text-lg font-medium">松手即新建材料包</p>
            <p className="mt-1 text-sm text-secondary-foreground">PDF · Word · 图片 · 视频，混着来都行</p>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className={cn('hidden')}
        onChange={(e) => {
          handleFiles(e.target.files)
          e.target.value = ''
        }}
      />

      {openId != null && <Reader />}

      {/* 卡片归案：归属 modal */}
      {assigning && (
        <AssignModal
          open
          count={assigning.segs}
          infos={[]}
          onCancel={() => setAssigning(null)}
          onConfirm={(assign: AssignInfo) => {
            const p = assigning
            setAssigning(null)
            judge(p, 'done') // 归案归属信息暂存于后端 draft_state.assign，办案端消费
            void assign
          }}
        />
      )}

      {/* 删除材料包：破坏性操作，右键菜单点击后先二次确认 */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除「{deleteTarget?.subject}」？</AlertDialogTitle>
            <AlertDialogDescription>
              将删除该材料包及其全部附件文件，不可恢复。已归案 / 归档关联不会被动，仅移除收件箱里的拆分草稿。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              disabled={deletePack.isPending}
              onClick={() => {
                const p = deleteTarget
                if (!p) return
                deletePack
                  .mutateAsync(p.id)
                  .then(() => {
                    toast(`${p.subject} 已删除`)
                    setDeleteTarget(null)
                  })
                  .catch(() => toast.error('删除失败，请重试'))
              }}
            >
              {deletePack.isPending ? '删除中…' : '删除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 重命名材料包：右键菜单打开 */}
      <RenamePackDialog open={!!renameTarget} onOpenChange={(o) => !o && setRenameTarget(null)} pack={renameTarget} />
    </div>
  )
}
