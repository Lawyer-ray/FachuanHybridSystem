import { useState, useRef, useCallback } from 'react'
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
  useReviewArticle,
  useReviewEpisode,
  useRetryTask,
  useCancelTask,
  useUpdateArticle,
  useRegenerateArticle,
} from '../hooks/use-content-ops'
import { STATUS_LABEL, REVIEW_STATUS_LABEL } from '../types'
import type { GeneratedArticle, PodcastEpisode, ReviewStatus } from '../types'
import { contentOpsApi } from '../api'
import { toast } from 'sonner'

interface TaskDetailProps {
  taskId: number
}

export function TaskDetail({ taskId }: TaskDetailProps) {
  const { data: task, isLoading } = useTaskDetail(taskId)
  const { data: articles = [] } = useTaskArticles(taskId)
  const { data: episodes = [] } = useTaskEpisodes(taskId)
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
            <Button
              size="sm"
              variant="outline"
              onClick={() => retryTask.mutate(task.id)}
              disabled={retryTask.isPending}
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1" />
              重试任务
            </Button>
          </CardContent>
        </Card>
      )}

      {/* 取消按钮 */}
      {isActive && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => cancelTask.mutate(task.id)}
          disabled={cancelTask.isPending}
        >
          <XCircle className="w-3.5 h-3.5 mr-1" />
          取消任务
        </Button>
      )}

      {/* 文章和音频 Tab */}
      {(articles.length > 0 || episodes.length > 0) && (
        <Tabs defaultValue="articles">
          <div className="flex items-center justify-between">
            <TabsList>
              <TabsTrigger value="articles">
                <FileText className="w-4 h-4 mr-1" />
                文章 ({articles.length})
              </TabsTrigger>
              <TabsTrigger value="episodes">
                <Volume2 className="w-4 h-4 mr-1" />
                音频 ({episodes.length})
              </TabsTrigger>
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

  const reviewBadge = (status: ReviewStatus) => {
    const variants = { draft: 'secondary' as const, approved: 'default' as const, rejected: 'destructive' as const }
    return <Badge variant={variants[status]}>{REVIEW_STATUS_LABEL[status]}</Badge>
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-sm">{article.title}</CardTitle>
            <CardDescription className="text-xs mt-0.5">
              {article.llm_model && <span>模型: {article.llm_model}</span>}
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

function EpisodeCard({ episode }: { episode: PodcastEpisode }) {
  const [playing, setPlaying] = useState(false)
  const [audioError, setAudioError] = useState(false)
  const [notes, setNotes] = useState('')
  const reviewEpisode = useReviewEpisode()
  const audioRef = useRef<HTMLAudioElement>(null)
  const audioUrl = contentOpsApi.getAudioUrl(episode.id)

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

  const reviewBadge = (status: ReviewStatus) => {
    const variants = { draft: 'secondary' as const, approved: 'default' as const, rejected: 'destructive' as const }
    return <Badge variant={variants[status]}>{REVIEW_STATUS_LABEL[status]}</Badge>
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              size="icon"
              variant="outline"
              className="h-8 w-8"
              onClick={handlePlay}
              disabled={audioError}
            >
              {audioError ? (
                <AlertCircle className="w-4 h-4 text-destructive" />
              ) : playing ? (
                <Pause className="w-4 h-4" />
              ) : (
                <Play className="w-4 h-4" />
              )}
            </Button>
            <div>
              <p className="text-sm font-medium">音色: {episode.voice}</p>
              <p className="text-[10px] text-muted-foreground">
                {episode.duration_seconds && `${Math.round(episode.duration_seconds)}秒`}
                {episode.file_size_bytes && ` · ${(episode.file_size_bytes / 1024 / 1024).toFixed(1)}MB`}
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

        <audio
          ref={audioRef}
          src={audioUrl ?? undefined}
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
      toast.success(`已批量通过 ${draftArticles.length} 篇文章和 ${draftEpisodes.length} 个音频`)
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
