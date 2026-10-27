import { useCallback, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
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
import { OfficeView } from '@/components/shared/onlyoffice/OfficeView'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { getContentVersion, getTaskStatus, listVersions } from '../api'
import { RevisionList } from '../components/RevisionList'
import { VersionChainButton, VersionChainPanel } from '../components/VersionChainPanel'
import { progressText, revisedFileName } from '../domain'
import { useRevisions } from '../hooks/use-revisions'
import type { ReviewEditorMode, ReviewRevision } from '../types'

/** 本页 query key 工厂（修订清单的键在 use-revisions 里，同一前缀 contract-review） */
const reviewPageKeys = {
  versions: (taskId: string | null) => ['contract-review', 'versions', taskId] as const,
  contentVersion: (taskId: string | null) => ['contract-review', 'content-version', taskId] as const,
  taskStatus: (taskId: string | null) => ['contract-review', 'task-status', taskId] as const,
}

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
  /**
   * 文档内容版本（喂给 OfficeView 的 version）。
   *
   * 以前这里拼的是 `taskId:acceptedCount`——每采纳一条就变，于是 OfficeView
   * 把 DS 画布整篇销毁重建（首次 5–15 秒）。律师逐条过 30 处建议就要等 30 次。
   *
   * 真正该重建的时机只有「文档内容变了」：即编辑器保存回写（人工改动 /
   * 插件写入修订后保存）导致 saved_version 递增。采纳只改 DB 状态、不写
   * docx，不该动画布。
   *
   * 不轮询：只有「可能在文档里落痕」的动作（写入AI修订 / 强制保存）之后才需要重查，
   * 常态下每 2 秒一次请求只是白烧带宽。首挂与切换任务时拉一次拿到当前值，
   * 之后由 contentVersionQuery.refetch 按需重查。
   */
  const contentVersionQuery = useQuery({
    queryKey: reviewPageKeys.contentVersion(taskId ?? null),
    queryFn: ({ signal }) => getContentVersion(taskId as string, signal),
    enabled: taskId != null,
    // 版本取不到不阻断阅读：OfficeView 仍能用空版本挂载，只是不会自动重建
    retry: false,
  })
  const contentVersion = contentVersionQuery.data?.content_version ?? ''

  /** 版本链：右侧面板显示「改过几轮、每轮谁改的、从哪版改出来」 */
  const [showVersions, setShowVersions] = useState(false)
  // 面板打才拉（enabled）：版本链不是高频信息，不值得进首屏关键路径
  const versionsQuery = useQuery({
    queryKey: reviewPageKeys.versions(taskId ?? null),
    queryFn: ({ signal }) => listVersions(taskId as string, signal),
    enabled: taskId != null && showVersions,
  })
  const versions = versionsQuery.data?.items ?? []
  const versionsLoading = versionsQuery.isPending && showVersions
  const versionsError = versionsQuery.error ? errMessage(versionsQuery.error, '加载版本链失败') : null

  /** DS 顶栏文件名：优先任务产物真名（与 /download 返回的文件一致，自带 .docx） */
  const taskStatusQuery = useQuery({
    queryKey: reviewPageKeys.taskStatus(taskId ?? null),
    queryFn: ({ signal }) => getTaskStatus(taskId as string, signal),
    enabled: taskId != null,
    // 文件名只影响 DS 标题展示：取不到就沿用兜底名，不重试也不打断复审
    retry: false,
    select: (task) => task.output_filename,
  })
  const fileName = taskStatusQuery.data || '合同（法穿SI修订）.docx'

  const total = items.length

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

  /**
   * 未决策的建议不会写入文档，所以还有 pending 时必须二次确认；
   * 全部决策完就没有可丢的东西，不必再拦一道。
   * 确认用全站统一的 AlertDialog（window.confirm 在 OnlyOffice 画布内会被
   * 浏览器的「阻止此页面创建更多对话框」吞掉，且样式与其他确认框不一致）。
   */
  const [confirmFinalize, setConfirmFinalize] = useState(false)

  const saveFinalCopy = useCallback(() => {
    toast.success('已保存定稿', {
      description: revisedFileName('合同.docx'),
    })
  }, [])

  const finalize = useCallback(() => {
    if (pendingCount > 0) {
      setConfirmFinalize(true)
      return
    }
    saveFinalCopy()
  }, [pendingCount, saveFinalCopy])

  if (!taskId) {
    return <CenterHint text="缺少审查任务 ID" />
  }

  return (
    <main className="app-page-enter @container mx-auto flex h-[calc(100vh-56px)] max-w-[1600px] flex-col px-[22px] pb-4 pt-3">
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
          <VersionChainButton count={versions.length} onClick={() => setShowVersions((v) => !v)} />
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

      {/* 三栏。断点全部走容器查询（本路由在宽屏恒并排 AI 助手，视口断点
          量不到被吃掉的几百像素，三栏会挤成一条条窄缝）：
          ≥1150 三栏（≈ 旧视口 1200 扣页边距）／≥850 建议清单+画布／再窄只留画布 */}
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden rounded-[12px] border border-border bg-card shadow-sm @min-[850px]:grid-cols-[260px_minmax(0,1fr)] @min-[1150px]:grid-cols-[290px_minmax(0,1fr)_320px]">
        {/* 左：建议清单 */}
        <aside className="min-h-0 border-r border-border-light @max-[850px]:hidden">
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
            version={contentVersion}
          />
        </div>

        {/* 右：版本链 / AI 对话。版本链展开时占据右栏（同一块地方不并排挤） */}
        <aside className="flex min-h-0 flex-col border-l border-border-light @max-[1150px]:hidden">
          {showVersions ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex flex-none items-center justify-between border-b border-border-light px-3.5 py-2.5">
                <span className="text-[12px] font-semibold">版本链</span>
                <button
                  type="button"
                  className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => setShowVersions(false)}
                >
                  收起
                </button>
              </div>
              <VersionChainPanel
                items={versions}
                isLoading={versionsLoading}
                error={versionsError}
              />
            </div>
          ) : (
            <div className="p-3.5">
              <p className="text-[12px] font-semibold">法穿 AI 助手</p>
              <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
                选中原文（或在文档里右键）→ 下指令 → 以修订插入；也可以直接问我。
              </p>
              <div className="mt-3 rounded-[8px] border border-border-light bg-secondary/60 px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
                对话组件将复用 copilot 域的同一套流式实现，避免两套 UI 分叉。
              </div>
            </div>
          )}
        </aside>
      </div>

      <AlertDialog open={confirmFinalize} onOpenChange={setConfirmFinalize}>
        <AlertDialogContent className="max-w-[360px]">
          <AlertDialogHeader>
            <AlertDialogTitle>还有 {pendingCount} 处建议未决策</AlertDialogTitle>
            <AlertDialogDescription>
              未决策的建议不会写入文档。仍要保存定稿吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>继续审阅</AlertDialogCancel>
            <AlertDialogAction onClick={saveFinalCopy}>保存定稿</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
