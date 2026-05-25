import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2, Search, FileText, Volume2, Users, Trash2, Plus } from 'lucide-react'
import { useCreateTask } from '../hooks/use-content-ops'
import { contentOpsApi } from '../api'
import { VOICE_OPTIONS, OUTPUT_MODE_LABEL } from '../types'
import type { TaskMode, OutputMode, DiscussionSpeaker } from '../types'
import { useCredentials } from '@/features/organization/hooks/use-credentials'
import { toast } from 'sonner'

const DEFAULT_SPEAKERS: DiscussionSpeaker[] = [
  { name: '主持人', role: '播客主持人，负责引导话题、提问、总结', style_prompt: '一个热情的播客主持人，声音清晰有力，语速适中，善于引导话题和提问' },
  { name: '张律师', role: '资深律师，负责法律分析和专业解读', style_prompt: '一个中年男性律师，声音沉稳专业，说话条理清晰，善于用通俗语言解释法律概念' },
  { name: '李大姐', role: '社区热心人，代表普通群众的视角，负责提出接地气的问题', style_prompt: '一个中年女性邻居，说话亲切自然，语速稍慢，带有生活气息和好奇心' },
]

interface CreateTaskDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultMode?: TaskMode
  defaultKeyword?: string
  defaultCaseSummary?: string
}

export function CreateTaskDialog({
  open,
  onOpenChange,
  defaultMode = 'direct',
  defaultKeyword = '',
  defaultCaseSummary = '',
}: CreateTaskDialogProps) {
  const [mode, setMode] = useState<TaskMode>(defaultMode)
  const [keyword, setKeyword] = useState(defaultKeyword)
  const [caseSummary, setCaseSummary] = useState(defaultCaseSummary)
  const [directContent, setDirectContent] = useState('')
  const [voice, setVoice] = useState('冰糖')
  const [credentialId, setCredentialId] = useState<number | null>(null)
  const [outputMode, setOutputMode] = useState<OutputMode>('narration')
  const [speakers, setSpeakers] = useState<DiscussionSpeaker[]>(DEFAULT_SPEAKERS)

  // Sync props when dialog opens
  useEffect(() => {
    if (open) {
      setMode(defaultMode)
      setKeyword(defaultKeyword)
      setCaseSummary(defaultCaseSummary)
    }
  }, [open, defaultMode, defaultKeyword, defaultCaseSummary])

  const createTask = useCreateTask()
  const { data: credentials = [] } = useCredentials()
  const [previewPlaying, setPreviewPlaying] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const handleVoicePreview = useCallback(async () => {
    if (previewPlaying && audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
      setPreviewPlaying(false)
      return
    }

    setPreviewLoading(true)
    try {
      const blob = await contentOpsApi.testTts('你好，我是你的法律故事播客主持人。', voice)
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => {
        setPreviewPlaying(false)
        URL.revokeObjectURL(url)
      }
      audio.onerror = () => {
        setPreviewPlaying(false)
        setPreviewLoading(false)
        URL.revokeObjectURL(url)
        toast.error('语音试听失败')
      }
      await audio.play()
      setPreviewPlaying(true)
    } catch {
      toast.error('语音试听失败')
    } finally {
      setPreviewLoading(false)
    }
  }, [voice, previewPlaying])

  // 过滤威科先行相关凭证
  const weikeCredentials = credentials.filter((c) => {
    const name = c.site_name.toLowerCase()
    return name.includes('wk') || name.includes('weike') || name.includes('wkinfo')
  })

  const handleSubmit = () => {
    if (mode === 'search') {
      if (!keyword.trim()) {
        toast.error('请输入检索关键词')
        return
      }
      if (!credentialId) {
        toast.error('请选择法律检索账号')
        return
      }
    }
    if (mode === 'direct' && !directContent.trim()) {
      toast.error('请输入内容')
      return
    }

    createTask.mutate(
      {
        mode,
        keyword: mode === 'search' ? keyword : undefined,
        credential_id: mode === 'search' ? credentialId : undefined,
        case_summary: caseSummary || undefined,
        direct_content: mode === 'direct' ? directContent : undefined,
        voice,
        output_mode: outputMode,
        discussion_speakers: outputMode !== 'narration' ? speakers : undefined,
      },
      {
        onSuccess: (task) => {
          toast.success(`任务 #${task.id} 已创建，正在处理中`)
          onOpenChange(false)
          resetForm()
        },
        onError: (error) => {
          toast.error(error instanceof Error ? error.message : '创建任务失败')
        },
      },
    )
  }

  const resetForm = () => {
    setKeyword('')
    setCaseSummary('')
    setDirectContent('')
    setVoice('冰糖')
    setCredentialId(null)
    setOutputMode('narration')
    setSpeakers(DEFAULT_SPEAKERS)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>创建内容任务</DialogTitle>
          <DialogDescription>
            {mode === 'search'
              ? 'AI 将通过关键词检索法律案例，然后生成叙事文章和音频'
              : 'AI 将把你的内容改写为叙事风格的文章并生成音频'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 模式切换 */}
          <div className="flex gap-2">
            <Button
              type="button"
              variant={mode === 'search' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMode('search')}
            >
              <Search className="w-4 h-4 mr-1" />
              检索模式
            </Button>
            <Button
              type="button"
              variant={mode === 'direct' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMode('direct')}
            >
              <FileText className="w-4 h-4 mr-1" />
              直投模式
            </Button>
          </div>

          {/* 检索模式字段 */}
          {mode === 'search' && (
            <>
              <div className="space-y-2">
                <Label>检索关键词 *</Label>
                <Input
                  placeholder="输入法律案例关键词，如：邻里纠纷、劳动仲裁"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>法律检索账号 *</Label>
                {weikeCredentials.length === 0 ? (
                  <p className="text-xs text-destructive">
                    未找到威科先行相关账号，请先在「组织管理 - 凭证管理」中添加
                  </p>
                ) : (
                  <Select
                    value={credentialId?.toString() ?? ''}
                    onValueChange={(v) => setCredentialId(Number(v))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="选择检索账号" />
                    </SelectTrigger>
                    <SelectContent>
                      {weikeCredentials.map((c) => (
                        <SelectItem key={c.id} value={c.id.toString()}>
                          {c.site_name} - {c.account}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </>
          )}

          {/* 直投模式字段 */}
          {mode === 'direct' && (
            <div className="space-y-2">
              <Label>输入内容 *</Label>
              <Textarea
                placeholder="粘贴案例内容、判决书摘要或任何法律文本..."
                value={directContent}
                onChange={(e) => setDirectContent(e.target.value)}
                rows={6}
              />
            </div>
          )}

          {/* 通用字段 */}
          <div className="space-y-2">
            <Label>案例摘要 <span className="text-muted-foreground">(可选)</span></Label>
            <Input
              placeholder="简要描述案例背景，帮助 AI 更好理解"
              value={caseSummary}
              onChange={(e) => setCaseSummary(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>语音音色</Label>
            <div className="flex gap-2">
              <Select value={voice} onValueChange={setVoice}>
                <SelectTrigger className="flex-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VOICE_OPTIONS.map((v) => (
                    <SelectItem key={v.value} value={v.value}>
                      {v.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={handleVoicePreview}
                disabled={previewLoading}
                title={previewPlaying ? '停止试听' : '试听语音'}
              >
                {previewLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : previewPlaying ? (
                  <span className="text-xs">停止</span>
                ) : (
                  <Volume2 className="w-4 h-4" />
                )}
              </Button>
            </div>
          </div>

          {/* 输出模式 */}
          <div className="space-y-2">
            <Label>输出模式</Label>
            <div className="flex gap-2">
              {(Object.entries(OUTPUT_MODE_LABEL) as [OutputMode, string][]).map(([key, label]) => (
                <Button
                  key={key}
                  type="button"
                  variant={outputMode === key ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setOutputMode(key)}
                >
                  {key === 'discussion' && <Users className="w-4 h-4 mr-1" />}
                  {label}
                </Button>
              ))}
            </div>
          </div>

          {/* 讨论角色配置 */}
          {outputMode !== 'narration' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>讨论角色</Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setSpeakers([...speakers, { name: '', role: '', style_prompt: '' }])}
                >
                  <Plus className="w-3.5 h-3.5 mr-1" />
                  添加角色
                </Button>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {speakers.map((speaker, idx) => (
                  <div key={idx} className="flex gap-2 items-start p-2 rounded-md border bg-muted/30">
                    <div className="flex-1 grid grid-cols-3 gap-2">
                      <Input
                        placeholder="角色名"
                        value={speaker.name}
                        onChange={(e) => {
                          const next = [...speakers]
                          next[idx] = { ...next[idx], name: e.target.value }
                          setSpeakers(next)
                        }}
                        className="h-8 text-xs"
                      />
                      <Input
                        placeholder="角色定位"
                        value={speaker.role}
                        onChange={(e) => {
                          const next = [...speakers]
                          next[idx] = { ...next[idx], role: e.target.value }
                          setSpeakers(next)
                        }}
                        className="h-8 text-xs"
                      />
                      <Input
                        placeholder="声音描述"
                        value={speaker.style_prompt}
                        onChange={(e) => {
                          const next = [...speakers]
                          next[idx] = { ...next[idx], style_prompt: e.target.value }
                          setSpeakers(next)
                        }}
                        className="h-8 text-xs"
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0"
                      onClick={() => setSpeakers(speakers.filter((_, i) => i !== idx))}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={createTask.isPending}>
            {createTask.isPending && <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />}
            创建任务
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
