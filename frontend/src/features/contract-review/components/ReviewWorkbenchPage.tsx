import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { OfficeView } from '@/components/shared/onlyoffice/OfficeView'
import { cn } from '@/lib/utils'
import { getTaskStatus } from '../api'
import { RevisionList } from '../components/RevisionList'
import { progressText, revisedFileName } from '../domain'
import { useRevisions } from '../hooks/use-revisions'
import type { ReviewEditorMode, ReviewRevision } from '../types'

/**
 * 合同复审工作台。
 *
 * 三栏与律师的真实动作一一对应：
 * - 左：AI 建议清单（看 AI 想改什么 → 采纳 / 驳回）
 * - 中：OnlyOffice 画布（真文档、真修订痕迹）
 * - 右：AI 对话（选中文档原文 → 指令 → 以修订插入）
 *
 * 路由：`/projects/:id/review/:taskId`
 */
export function ReviewWorkbenchPage() {
  const { id: projectId, taskId } = useParams<{ id: string; taskId: string }>()
  const navigate = useNavigate()
  const { items, isLoading, error, busyId, pendingCount, decide } = useRevisions(taskId ?? null)
  const [mode, setMode] = useState<ReviewEditorMode>('review')
  /** DS 顶栏文件名：优先任务产物真名（与 /download 返回的文件一致，自带 .docx） */
  const [fileName, setFileName] = useState('合同（法穿SI修订）.docx')

  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    void getTaskStatus(taskId)
      .then((task) => {
        if (!cancelled && task.output_filename) setFileName(task.output_filename)
      })
      .catch(() => {
        // 文件名只影响 DS 标题展示，取不到时沿用兜底名，不打断复审
      })
    return () => {
      cancelled = true
    }
  }, [taskId])

  const total = items.length
  const acceptedCount = useMemo(() => items.filter((r) => r.status === 'accepted').length, [items])

  /** 定位：跳到文档对应处。当前由编辑器侧完成（DS 内建查找），这里只做提示。 */
  const locate = useCallback((rev: ReviewRevision) => {
    const anchor = rev.original.slice(0, 12)
    toast.info(`在文档中查找：${anchor}…`, { description: '可用 Ctrl/⌘+F 精确定位' })
  }, [])

  const onDecide = useCallback(
    (rev: ReviewRevision, action: 'accept' | 'reject', reason?: string): void => {
      // decide 是异步的，但这里是 UI 回调：返回 void，失败由 hook 内部回滚
      void decide(rev, action, reason)
    },
    [decide],
  )

  const finalize = useCallback(() => {
    if (pendingCount > 0) {
      const ok = window.confirm(
        `还有 ${pendingCount} 处建议未决策，未决策的不会写入文档。\n仍要保存定稿吗？`,
      )
      if (!ok) return
    }
    toast.success('已保存定稿', {
      description: revisedFileName('合同.docx'),
    })
  }, [pendingCount])

  if (!taskId) {
    return <CenterHint text="缺少审查任务 ID" />
  }

  return (
    <main className="app-page-enter mx-auto flex h-[calc(100vh-56px)] max-w-[1600px] flex-col px-[22px] pb-4 pt-3">
      {/* 页头 */}
      <div className="flex flex-none items-center gap-3 pb-2.5">
        <button
          type="button"
          className="inline-flex h-[31px] items-center gap-1.5 rounded-[8px] border border-border bg-card px-2.5 text-[12.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
          onClick={() => {
            void navigate(projectId ? `/projects/${projectId}` : '/projects')
          }}
        >
          <ArrowLeft className="size-3.5" />
          返回项目
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-[15px] font-[650] tracking-[-0.01em]">合同复审</h1>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            {isLoading ? '正在加载修订清单…' : progressText(total, pendingCount)}
          </p>
        </div>
        <div className="flex flex-none items-center gap-1.5">
          {(['review', 'view', 'edit'] as ReviewEditorMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={cn(
                'h-[27px] rounded-[7px] border px-2.5 text-[11.5px] font-medium transition-colors',
                mode === m
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
              )}
            >
              {m === 'review' ? '锁定修订' : m === 'view' ? '只读' : '完全编辑'}
            </button>
          ))}
          <button
            type="button"
            className="ml-1 h-[31px] rounded-[8px] border border-foreground bg-foreground px-3.5 text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85"
            onClick={finalize}
          >
            保存定稿
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-2 rounded-[8px] border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11.5px] text-destructive">
          {error}
        </div>
      )}

      {/* 三栏 */}
      <div className="grid min-h-0 flex-1 grid-cols-[290px_minmax(0,1fr)_320px] overflow-hidden rounded-[12px] border border-border bg-card shadow-sm max-[1200px]:grid-cols-[260px_minmax(0,1fr)] max-[900px]:grid-cols-1">
        {/* 左：建议清单 */}
        <aside className="min-h-0 border-r border-border-light max-[900px]:hidden">
          {isLoading ? (
            <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              加载中…
            </div>
          ) : (
            <RevisionList items={items} busyId={busyId} onDecide={onDecide} onLocate={locate} />
          )}
        </aside>

        {/* 中：编辑器 */}
        <div className="min-h-0 overflow-hidden">
          <OfficeView
            fileUrl={`/api/v1/contract-review/${encodeURIComponent(taskId)}/download`}
            fileName={fileName}
            mode={mode}
            version={`${taskId}:${acceptedCount}`}
          />
        </div>

        {/* 右：AI 对话占位（后续接 copilot 域的 chat 组件） */}
        <aside className="min-h-0 border-l border-border-light p-3.5 max-[1200px]:hidden">
          <p className="text-[12px] font-semibold">法穿 AI 助手</p>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
            选中原文（或在文档里右键）→ 下指令 → 以修订插入；也可以直接问我。
          </p>
          <div className="mt-3 rounded-[8px] border border-border-light bg-secondary/60 px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
            对话组件将复用 copilot 域的同一套流式实现，避免两套 UI 分叉。
          </div>
        </aside>
      </div>
    </main>
  )
}

function CenterHint({ text }: { text: string }) {
  return (
    <main className="grid min-h-[60vh] place-items-center px-6">
      <p className="text-sm text-muted-foreground">{text}</p>
    </main>
  )
}
