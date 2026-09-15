import { useRef, useState } from 'react'
import { Loader2, LogOut, PackagePlus, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/store'
import { useMaterialPacks, useCreatePack } from '../hooks/use-inbox'
import { useReader } from '../store'
import { PackCard } from './PackCard'
import { Reader } from './reader/Reader'
import { cn } from '@/lib/utils'

export function DeskPage() {
  const { data: packs, isLoading, error } = useMaterialPacks()
  const createPack = useCreatePack()
  const { user, logout } = useAuth()
  const openPack = useReader((s) => s.open)
  const openId = useReader((s) => s.openId)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const deskRef = useRef<HTMLDivElement>(null)
  const dragDepth = useRef(0)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      await createPack.mutateAsync(Array.from(files))
      toast.success(`已收进 ${files.length} 份材料`)
    } catch {
      toast.error('上传失败，请检查后端连接')
    } finally {
      setUploading(false)
      setDragging(false)
    }
  }

  return (
    <div
      ref={deskRef}
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
      {/* 顶部导航 */}
      <header className="sticky top-0 z-20 flex h-[54px] items-center gap-6 border-b border-border bg-card px-7">
        <div className="flex flex-none items-center gap-2.5">
          <span className="text-[13.5px] font-semibold tracking-tight">
            法穿 <span className="font-medium">AI Copilot</span>
          </span>
        </div>
        <nav className="flex flex-1 items-center gap-0.5">
          <span className="rounded-[7px] bg-secondary px-3 py-1.5 text-[13.5px] font-medium text-foreground">
            材料预处理
          </span>
        </nav>
        <div className="flex flex-none items-center gap-2">
          {user?.username ? (
            <span className="hidden text-xs text-secondary-foreground sm:inline">{user.username}</span>
          ) : null}
          <Button size="sm" onClick={() => logout()}>
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">退出</span>
          </Button>
        </div>
      </header>

      <main className="relative px-7 pb-24 pt-6">
        <div className="mb-5 flex flex-wrap items-center gap-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">材料预处理</h1>
            <p className="mt-0.5 text-xs text-secondary-foreground">待拆的材料包 · 全部靠手划，机器不猜</p>
          </div>
          <div className="ml-auto">
            <Button onClick={() => fileInputRef.current?.click()} disabled={uploading}>
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
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-4">
            {packs?.map((p) => (
              <PackCard key={p.id} pack={p} onOpen={() => openPack(p.id)} />
            ))}
            {/* 虚线槽：第二个新建入口 + 空状态 */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex min-h-[280px] cursor-pointer flex-col items-center justify-center gap-2.5 rounded-[13px] border-[1.5px] border-dashed border-zinc-300 text-secondary-foreground transition-colors hover:border-zinc-400 hover:bg-card hover:text-foreground"
            >
              <span className="grid h-[34px] w-[34px] place-items-center rounded-[9px] bg-secondary text-secondary-foreground">
                <Plus className="h-4 w-4" />
              </span>
              <span className="text-sm">拖入材料，或点这里选文件</span>
              <span className="text-[11.5px] text-muted-foreground">PDF · Word · 图片，混着来都行</span>
            </button>
          </div>
        )}
      </main>

      {/* 拖放遮罩 */}
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-foreground/20 backdrop-blur-[1px]">
          <div className="rounded-2xl border border-primary bg-card px-10 py-8 text-center shadow-xl">
            <p className="text-lg font-medium">松手即新建材料包</p>
            <p className="mt-1 text-sm text-secondary-foreground">PDF · Word · 图片，混着来都行</p>
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
    </div>
  )
}
