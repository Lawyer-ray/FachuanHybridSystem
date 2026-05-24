import { useState, useRef, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  Loader2,
  FileText,
  Volume2,
  Play,
  Pause,
  Download,
  ThumbsUp,
  ThumbsDown,
  Copy,
  Check,
  AlertCircle,
  RotateCcw,
  XCircle,
  Pencil,
  RefreshCw,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useTaskDetail,
  useTaskArticles,
  useTaskEpisodes,
  useTaskDiscussions,
  useReviewArticle,
  useReviewEpisode,
  useReviewDiscussion,
  useRetryTask,
  useCancelTask,
  useUpdateArticle,
  useRegenerateArticle,
  useUpdateDiscussionTurn,
  useRegenerateDiscussion,
  useSynthesizeDiscussion,
} from '../hooks/use-content-ops'
import { STATUS_LABEL, REVIEW_STATUS_LABEL } from '../types'
import type { GeneratedArticle, PodcastEpisode, DiscussionScript, ReviewStatus } from '../types'
import { contentOpsApi } from '../api'
import { toast } from 'sonner'

interface TaskDetailProps {
  taskId: number
}

export function TaskDetail({ taskId }: TaskDetailProps) {
  const { data: task, isLoading } = useTaskDetail(taskId)
  const { data: articles = [] } = useTaskArticles(taskId)
  const { data: episodes = [] } = useTaskEpisodes(taskId)
  const { data: discussions = [] } = useTaskDiscussions(taskId)
  const retryTask = useRetryTask()
  const cancelTask = useCancelTask()

  if (isLoading || !task) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const isActive = ['pending', 'queued', 'running'].includes(task.status)

  return (
    <div className="space-y-4">
      {/* 任务头部信息 */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold">
            {task.source_title || task.keyword || `任务 #${task.id}`}
          </h3>
          <Badge variant={task.status === 'completed' ? 'default' : task.status === 'failed' ? 'destructive' : 'secondary'}>
            {STATUS_LABEL[task.status]}
          </Badge>
        </div>
        {task.source_court_text && (
          <p className="text-xs text-muted-foreground">
            {task.source_court_text}
            {task.source_judgment_date && ` · ${task.source_judgment_date}`}
          </p>
        )}
      </div>

      {/* 进度条 */}
      {isActive && (
        <Card>
          <CardContent className="pt-4 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{task.message || '处理中...'}</span>
              <span className="font-medium">{task.progress}%</span>
            </div>
            <Progress value={task.progress} />
          </CardContent>
        </Card>
      )}

      {/* 错误信息 + 重试 */}
      {task.status === 'failed' && task.error && (
        <Card className="border-destructive/50">
          <CardContent className="pt-4 space-y-3">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
              <p className="text-sm text-destructive">{task.error}</p>
            </div>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button size="sm" variant="outline" disabled={retryTask.isPending}>
                  <RotateCcw className="w-3.5 h-3.5 mr-1" />
                  重试任务
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>确认重试任务？</AlertDialogTitle>
                  <AlertDialogDescription>
                    重试将删除已生成的文章和音频，重新执行整个流程。此操作不可撤销。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>取消</AlertDialogCancel>
                  <AlertDialogAction onClick={() => retryTask.mutate(task.id)}>
                    确认重试
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </CardContent>
        </Card>
      )}

      {/* 取消按钮 */}
      {isActive && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button size="sm" variant="outline" disabled={cancelTask.isPending}>
              <XCircle className="w-3.5 h-3.5 mr-1" />
              取消任务
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>确认取消任务？</AlertDialogTitle>
              <AlertDialogDescription>
                取消后任务将立即停止，已生成的部分内容会保留。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>继续执行</AlertDialogCancel>
              <AlertDialogAction onClick={() => cancelTask.mutate(task.id)}>
                确认取消
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}

      {/* 文章、音频、讨论稿 Tab */}
      {(articles.length > 0 || episodes.length > 0 || discussions.length > 0) && (
        <Tabs defaultValue={discussions.length > 0 ? 'discussions' : 'articles'}>
          <div className="flex items-center justify-between gap-2">
            <TabsList className="min-w-0">
              {articles.length > 0 && (
                <TabsTrigger value="articles" className="text-xs">
                  <FileText className="w-3.5 h-3.5 mr-1" />
                  文章 ({articles.length})
                </TabsTrigger>
              )}
              {discussions.length > 0 && (
                <TabsTrigger value="discussions" className="text-xs">
                  <FileText className="w-3.5 h-3.5 mr-1" />
                  讨论稿 ({discussions.length})
                </TabsTrigger>
              )}
              {episodes.length > 0 && (
                <TabsTrigger value="episodes" className="text-xs">
                  <Volume2 className="w-3.5 h-3.5 mr-1" />
                  音频 ({episodes.length})
                </TabsTrigger>
              )}
            </TabsList>
            <BatchApproveButton
              articles={articles}
              episodes={episodes}
            />
          </div>

          <TabsContent value="articles" className="space-y-3 mt-3">
            <motion.div
              className="space-y-3"
              initial="hidden"
              animate="visible"
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.06 } },
              }}
            >
              {articles.map((article) => (
                <motion.div
                  key={article.id}
                  variants={{
                    hidden: { opacity: 0, y: 8 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                >
                  <ArticleCard article={article} />
                </motion.div>
              ))}
            </motion.div>
          </TabsContent>

          <TabsContent value="episodes" className="space-y-3 mt-3">
            <motion.div
              className="space-y-3"
              initial="hidden"
              animate="visible"
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.06 } },
              }}
            >
              {episodes.map((episode) => (
                <motion.div
                  key={episode.id}
                  variants={{
                    hidden: { opacity: 0, y: 8 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                >
                  <EpisodeCard episode={episode} />
                </motion.div>
              ))}
            </motion.div>
          </TabsContent>

          <TabsContent value="discussions" className="space-y-3 mt-3">
            <motion.div
              className="space-y-3"
              initial="hidden"
              animate="visible"
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.06 } },
              }}
            >
              {discussions.map((script) => (
                <motion.div
                  key={script.id}
                  variants={{
                    hidden: { opacity: 0, y: 8 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                >
                  <DiscussionScriptCard script={script} />
                </motion.div>
              ))}
            </motion.div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

function ArticleCard({ article }: { article: GeneratedArticle }) {
  const [expanded, setExpanded] = useState(false)
  const [notes, setNotes] = useState('')
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const reviewArticle = useReviewArticle()
  const updateArticle = useUpdateArticle()
  const regenerateArticle = useRegenerateArticle()

  const handleReview = (action: 'approve' | 'reject') => {
    reviewArticle.mutate(
      { articleId: article.id, action, notes: notes || undefined },
      {
        onSuccess: () => {
          toast.success(action === 'approve' ? '文章已通过' : '文章已驳回')
          setNotes('')
        },
        onError: () => toast.error('操作失败'),
      },
    )
  }

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(article.content)
      setCopied(true)
      toast.success('已复制到剪贴板')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('复制失败')
    }
  }, [article.content])

  const startEdit = useCallback(() => {
    setEditTitle(article.title)
    setEditContent(article.content)
    setEditing(true)
  }, [article.title, article.content])

  const saveEdit = useCallback(() => {
    updateArticle.mutate(
      { articleId: article.id, title: editTitle, content: editContent },
      {
        onSuccess: () => {
          setEditing(false)
          toast.success('文章已更新')
        },
        onError: () => toast.error('保存失败'),
      },
    )
  }, [article.id, editTitle, editContent, updateArticle])

  const handleRegenerate = useCallback(() => {
    regenerateArticle.mutate(article.id, {
      onSuccess: () => toast.success('文章已重新生成'),
      onError: () => toast.error('重新生成失败'),
    })
  }, [article.id, regenerateArticle])

  const wordCount = article.content.length
  const readingTime = Math.max(1, Math.ceil(wordCount / 300))

  const reviewBadge = (status: ReviewStatus) => {
    const variants = { draft: 'secondary' as const, approved: 'default' as const, rejected: 'destructive' as const }
    return <Badge variant={variants[status]}>{REVIEW_STATUS_LABEL[status]}</Badge>
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-sm truncate">{article.title}</CardTitle>
            <CardDescription className="text-xs mt-0.5">
              <span>{wordCount} 字 · 约 {readingTime} 分钟</span>
              {article.llm_model && <span className="ml-2">模型: {article.llm_model}</span>}
              {article.token_usage && (
                <span className="ml-2">Token: {article.token_usage.total_tokens}</span>
              )}
            </CardDescription>
          </div>
          {reviewBadge(article.review_status)}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {article.source_summary && !editing && (
          <p className="text-xs text-muted-foreground italic">{article.source_summary}</p>
        )}

        {editing ? (
          <div className="space-y-2">
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              placeholder="文章标题"
              className="text-sm font-medium"
            />
            <Textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              rows={12}
              className="text-sm"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={saveEdit} disabled={updateArticle.isPending}>
                {updateArticle.isPending && <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />}
                保存
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                取消
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className={cn('text-sm whitespace-pre-wrap', !expanded && 'line-clamp-6')}>
              {article.content}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {article.content.length > 300 && (
                <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
                  {expanded ? '收起' : '展开全文'}
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={handleCopy}>
                {copied ? <Check className="w-3.5 h-3.5 mr-1" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                {copied ? '已复制' : '复制全文'}
              </Button>
              {article.review_status === 'draft' && (
                <>
                  <Button variant="outline" size="sm" onClick={startEdit}>
                    <Pencil className="w-3.5 h-3.5 mr-1" />
                    编辑
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRegenerate}
                    disabled={regenerateArticle.isPending}
                  >
                    {regenerateArticle.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5 mr-1" />
                    )}
                    重新生成
                  </Button>
                </>
              )}
            </div>
          </>
        )}

        {/* 审核操作 */}
        {article.review_status === 'draft' && !editing && (
          <div className="space-y-2 pt-2 border-t">
            <Textarea
              placeholder="审核备注（可选）"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="text-xs"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="default"
                onClick={() => handleReview('approve')}
                disabled={reviewArticle.isPending}
              >
                <ThumbsUp className="w-3.5 h-3.5 mr-1" />
                通过
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => handleReview('reject')}
                disabled={reviewArticle.isPending}
              >
                <ThumbsDown className="w-3.5 h-3.5 mr-1" />
                驳回
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const

function formatTime(sec: number): string {
  if (!Number.isFinite(sec)) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function EpisodeCard({ episode }: { episode: PodcastEpisode }) {
  const [playing, setPlaying] = useState(false)
  const [audioError, setAudioError] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [notes, setNotes] = useState('')
  const reviewEpisode = useReviewEpisode()
  const audioRef = useRef<HTMLAudioElement>(null)
  const progressRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)
  const audioUrl = contentOpsApi.getAudioUrl(episode.id)

  useEffect(() => {
    return () => {
      const audio = audioRef.current
      if (audio && !audio.paused) {
        audio.pause()
        audio.currentTime = 0
      }
    }
  }, [])

  const handleReview = (action: 'approve' | 'reject') => {
    reviewEpisode.mutate(
      { episodeId: episode.id, action, notes: notes || undefined },
      {
        onSuccess: () => {
          toast.success(action === 'approve' ? '音频已通过' : '音频已驳回')
          setNotes('')
        },
        onError: () => toast.error('操作失败'),
      },
    )
  }

  const handlePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (playing) {
      audio.pause()
      setPlaying(false)
    } else {
      audio.play().catch(() => {
        setAudioError(true)
        setPlaying(false)
        toast.error('音频播放失败')
      })
      setPlaying(true)
    }
  }, [playing])

  const handleSeek = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const bar = progressRef.current
    const audio = audioRef.current
    if (!bar || !audio || !duration) return
    const rect = bar.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    audio.currentTime = ratio * duration
    setCurrentTime(audio.currentTime)
  }, [duration])

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    isDragging.current = true
    handleSeek(e)

    const onMove = (ev: MouseEvent) => {
      if (!isDragging.current || !progressRef.current || !audioRef.current || !duration) return
      const rect = progressRef.current.getBoundingClientRect()
      const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
      audioRef.current.currentTime = ratio * duration
      setCurrentTime(audioRef.current.currentTime)
    }

    const onUp = () => {
      isDragging.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [duration, handleSeek])

  const handleSpeedChange = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    const idx = SPEED_OPTIONS.indexOf(speed as (typeof SPEED_OPTIONS)[number])
    const next = SPEED_OPTIONS[(idx + 1) % SPEED_OPTIONS.length]
    audio.playbackRate = next
    setSpeed(next)
  }, [speed])

  const reviewBadge = (status: ReviewStatus) => {
    const variants = { draft: 'secondary' as const, approved: 'default' as const, rejected: 'destructive' as const }
    return <Badge variant={variants[status]}>{REVIEW_STATUS_LABEL[status]}</Badge>
  }

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        {/* 顶部信息栏 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div>
              <p className="text-sm font-medium">音色: {episode.voice}</p>
              <p className="text-[10px] text-muted-foreground">
                {episode.file_size_bytes && `${(episode.file_size_bytes / 1024 / 1024).toFixed(1)}MB`}
                {audioError && <span className="text-destructive ml-1">音频加载失败</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {reviewBadge(episode.review_status)}
            <a href={audioUrl ?? undefined} download>
              <Button size="icon" variant="ghost" className="h-8 w-8">
                <Download className="w-4 h-4" />
              </Button>
            </a>
          </div>
        </div>

        {/* 播放器 */}
        <div className="bg-muted/50 rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-3">
            {/* 播放/暂停 */}
            <Button
              size="icon"
              variant="outline"
              className="h-9 w-9 shrink-0 rounded-full"
              onClick={handlePlay}
              disabled={audioError}
            >
              {audioError ? (
                <AlertCircle className="w-4 h-4 text-destructive" />
              ) : playing ? (
                <Pause className="w-4 h-4" />
              ) : (
                <Play className="w-4 h-4 ml-0.5" />
              )}
            </Button>

            {/* 进度条 */}
            <div className="flex-1 min-w-0">
              <div
                ref={progressRef}
                className="relative h-1.5 bg-muted rounded-full cursor-pointer group"
                onMouseDown={handleMouseDown}
              >
                <div
                  className="absolute inset-y-0 left-0 bg-primary rounded-full transition-none"
                  style={{ width: `${progress}%` }}
                />
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-primary rounded-full shadow opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ left: `calc(${progress}% - 6px)` }}
                />
              </div>
            </div>

            {/* 时间 */}
            <span className="text-[11px] text-muted-foreground tabular-nums shrink-0 w-[72px] text-right">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>

          <div className="flex items-center justify-between">
            {/* 音色信息 */}
            <p className="text-[10px] text-muted-foreground">
              {episode.duration_seconds && `${Math.round(episode.duration_seconds)}秒`}
            </p>

            {/* 倍速按钮 */}
            <button
              onClick={handleSpeedChange}
              className="text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors px-1.5 py-0.5 rounded hover:bg-muted"
            >
              {speed}x
            </button>
          </div>
        </div>

        <audio
          ref={audioRef}
          src={audioUrl ?? undefined}
          onTimeUpdate={() => {
            if (!isDragging.current && audioRef.current) {
              setCurrentTime(audioRef.current.currentTime)
            }
          }}
          onLoadedMetadata={() => {
            if (audioRef.current) {
              setDuration(audioRef.current.duration)
              audioRef.current.playbackRate = speed
            }
          }}
          onEnded={() => setPlaying(false)}
          onError={() => {
            setAudioError(true)
            setPlaying(false)
          }}
          className="hidden"
        />

        {/* 审核操作 */}
        {episode.review_status === 'draft' && (
          <div className="space-y-2 pt-2 border-t">
            <Textarea
              placeholder="审核备注（可选）"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="text-xs"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="default"
                onClick={() => handleReview('approve')}
                disabled={reviewEpisode.isPending}
              >
                <ThumbsUp className="w-3.5 h-3.5 mr-1" />
                通过
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => handleReview('reject')}
                disabled={reviewEpisode.isPending}
              >
                <ThumbsDown className="w-3.5 h-3.5 mr-1" />
                驳回
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function DiscussionScriptCard({ script }: { script: DiscussionScript }) {
  const [editingTurnId, setEditingTurnId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [notes, setNotes] = useState('')
  const updateTurn = useUpdateDiscussionTurn()
  const reviewDiscussion = useReviewDiscussion()
  const regenerateDiscussion = useRegenerateDiscussion()
  const synthesizeDiscussion = useSynthesizeDiscussion()

  const handleEditTurn = (turnId: number, text: string) => {
    setEditingTurnId(turnId)
    setEditText(text)
  }

  const handleSaveTurn = () => {
    if (editingTurnId === null) return
    updateTurn.mutate(
      { turnId: editingTurnId, text: editText },
      {
        onSuccess: () => {
          setEditingTurnId(null)
          toast.success('对话已更新')
        },
        onError: () => toast.error('保存失败'),
      },
    )
  }

  const handleReview = (action: 'approve' | 'reject') => {
    reviewDiscussion.mutate(
      { scriptId: script.id, action, notes: notes || undefined },
      {
        onSuccess: () => {
          toast.success(action === 'approve' ? '讨论稿已通过' : '讨论稿已驳回')
          setNotes('')
        },
        onError: () => toast.error('操作失败'),
      },
    )
  }

  const handleRegenerate = () => {
    regenerateDiscussion.mutate(script.id, {
      onSuccess: () => toast.success('讨论稿已重新生成'),
      onError: () => toast.error('重新生成失败'),
    })
  }

  const handleSynthesize = () => {
    synthesizeDiscussion.mutate(script.id, {
      onSuccess: () => toast.success('音频合成完成'),
      onError: (err) => toast.error(`合成失败: ${err instanceof Error ? err.message : '未知错误'}`),
    })
  }

  const reviewBadge = (status: ReviewStatus) => {
    const variants = { draft: 'secondary' as const, approved: 'default' as const, rejected: 'destructive' as const }
    return <Badge variant={variants[status]}>{REVIEW_STATUS_LABEL[status]}</Badge>
  }

  // Generate consistent colors for speakers
  const speakerColors = [
    'bg-blue-100 text-blue-900 dark:bg-blue-900/30 dark:text-blue-300',
    'bg-green-100 text-green-900 dark:bg-green-900/30 dark:text-green-300',
    'bg-purple-100 text-purple-900 dark:bg-purple-900/30 dark:text-purple-300',
    'bg-orange-100 text-orange-900 dark:bg-orange-900/30 dark:text-orange-300',
    'bg-pink-100 text-pink-900 dark:bg-pink-900/30 dark:text-pink-300',
  ]
  const speakerColorMap = new Map<string, string>()
  const uniqueSpeakers = [...new Set(script.turns.map((t) => t.speaker_name))]
  uniqueSpeakers.forEach((name, i) => {
    speakerColorMap.set(name, speakerColors[i % speakerColors.length])
  })

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-sm truncate">{script.title}</CardTitle>
            {script.topic && <CardDescription className="text-xs mt-0.5 line-clamp-2">{script.topic}</CardDescription>}
            <CardDescription className="text-xs mt-0.5">
              {script.turns.length} 轮对话
              {script.llm_model && <span className="ml-2">模型: {script.llm_model}</span>}
              {script.token_usage && <span className="ml-2">Token: {script.token_usage.total_tokens}</span>}
            </CardDescription>
          </div>
          {reviewBadge(script.review_status)}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Chat bubble style turns */}
        <div className="space-y-2 max-h-96 overflow-y-auto p-1">
          {script.turns.map((turn) => {
            const colorClass = speakerColorMap.get(turn.speaker_name) || speakerColors[0]
            const isEditing = editingTurnId === turn.id
            return (
              <div key={turn.id} className="flex gap-2 group">
                <div className={cn('px-2 py-0.5 rounded text-xs font-medium shrink-0 self-start mt-1', colorClass)}>
                  {turn.speaker_name}
                </div>
                <div className="flex-1 min-w-0">
                  {isEditing ? (
                    <div className="space-y-1">
                      <Textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        rows={3}
                        className="text-sm"
                      />
                      <div className="flex gap-1">
                        <Button size="sm" className="h-6 text-xs" onClick={handleSaveTurn} disabled={updateTurn.isPending}>
                          保存
                        </Button>
                        <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setEditingTurnId(null)}>
                          取消
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {turn.text}
                      {script.review_status === 'draft' && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 ml-1 opacity-0 group-hover:opacity-100 inline-flex align-middle"
                          onClick={() => handleEditTurn(turn.id, turn.text)}
                        >
                          <Pencil className="w-3 h-3" />
                        </Button>
                      )}
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-wrap pt-2 border-t">
          {script.review_status === 'draft' && (
            <>
              <Button variant="outline" size="sm" onClick={handleRegenerate} disabled={regenerateDiscussion.isPending}>
                {regenerateDiscussion.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5 mr-1" />
                )}
                重新生成
              </Button>
              <Button variant="outline" size="sm" onClick={handleSynthesize} disabled={synthesizeDiscussion.isPending}>
                {synthesizeDiscussion.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                ) : (
                  <Volume2 className="w-3.5 h-3.5 mr-1" />
                )}
                合成音频
              </Button>
            </>
          )}
        </div>

        {/* Review actions */}
        {script.review_status === 'draft' && (
          <div className="space-y-2 pt-2 border-t">
            <Textarea
              placeholder="审核备注（可选）"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="text-xs"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="default"
                onClick={() => handleReview('approve')}
                disabled={reviewDiscussion.isPending}
              >
                <ThumbsUp className="w-3.5 h-3.5 mr-1" />
                通过
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => handleReview('reject')}
                disabled={reviewDiscussion.isPending}
              >
                <ThumbsDown className="w-3.5 h-3.5 mr-1" />
                驳回
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function BatchApproveButton({ articles, episodes }: {
  articles: GeneratedArticle[]
  episodes: PodcastEpisode[]
}) {
  const queryClient = useQueryClient()
  const draftArticles = articles.filter((a) => a.review_status === 'draft')
  const draftEpisodes = episodes.filter((e) => e.review_status === 'draft')

  const handleBatchApprove = async () => {
    try {
      if (draftArticles.length > 0) {
        await contentOpsApi.batchApproveArticles(draftArticles.map((a) => a.id))
      }
      if (draftEpisodes.length > 0) {
        await contentOpsApi.batchApproveEpisodes(draftEpisodes.map((e) => e.id))
      }
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
      const parts: string[] = []
      if (draftArticles.length > 0) parts.push(`${draftArticles.length} 篇文章`)
      if (draftEpisodes.length > 0) parts.push(`${draftEpisodes.length} 个音频`)
      toast.success(`已批量通过 ${parts.join('和')}`)
    } catch {
      toast.error('批量操作失败')
    }
  }

  if (draftArticles.length === 0 && draftEpisodes.length === 0) {
    return null
  }

  return (
    <Button size="sm" variant="outline" onClick={handleBatchApprove}>
      <Check className="w-3.5 h-3.5 mr-1" />
      一键全部通过 ({draftArticles.length + draftEpisodes.length})
    </Button>
  )
}
