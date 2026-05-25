import { useState } from 'react'
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
import { Loader2, Send } from 'lucide-react'
import { useCreateTask } from '../hooks/use-content-ops'
import { VOICE_OPTIONS } from '../types'
import { toast } from 'sonner'

interface DirectInputProps {
  onTaskCreated?: (taskId: number) => void
}

export function DirectInput({ onTaskCreated }: DirectInputProps) {
  const [content, setContent] = useState('')
  const [caseSummary, setCaseSummary] = useState('')
  const [voice, setVoice] = useState('冰糖')

  const createTask = useCreateTask()

  const handleSubmit = () => {
    if (!content.trim()) {
      toast.error('请输入内容')
      return
    }

    createTask.mutate(
      {
        mode: 'direct',
        direct_content: content,
        case_summary: caseSummary || undefined,
        voice,
      },
      {
        onSuccess: (task) => {
          toast.success(`任务 #${task.id} 已创建，正在处理中`)
          setContent('')
          setCaseSummary('')
          onTaskCreated?.(task.id)
        },
        onError: (error) => {
          toast.error(error instanceof Error ? error.message : '创建任务失败')
        },
      },
    )
  }

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label className="text-xs">输入内容 *</Label>
        <Textarea
          placeholder="粘贴判决书摘要、案例事实或任何法律文本..."
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={6}
          className="resize-none text-sm"
        />
        <p className="text-[10px] text-muted-foreground text-right">
          {content.length} 字
        </p>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">案例摘要 <span className="text-muted-foreground">(可选)</span></Label>
        <Input
          placeholder="简要描述案例背景"
          value={caseSummary}
          onChange={(e) => setCaseSummary(e.target.value)}
          className="h-8 text-sm"
        />
      </div>

      <div className="flex items-end gap-2">
        <div className="space-y-1.5 flex-1">
          <Label className="text-xs">语音音色</Label>
          <Select value={voice} onValueChange={setVoice}>
            <SelectTrigger className="h-8 text-sm">
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
        </div>

        <Button onClick={handleSubmit} disabled={createTask.isPending} size="sm" className="h-8 shrink-0">
          {createTask.isPending ? (
            <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
          ) : (
            <Send className="w-3.5 h-3.5 mr-1" />
          )}
          生成
        </Button>
      </div>
    </div>
  )
}
