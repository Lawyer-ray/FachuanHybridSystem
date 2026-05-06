/* eslint-disable react-refresh/only-export-components */
import { useState, useRef, useCallback } from 'react'
import { FolderOpen, X, FileText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'

interface BatchAnalysisDialogProps {
  modelName: string
  onSubmit: (prompt: string, files: File[]) => Promise<void>
  disabled?: boolean
}

export function BatchAnalysisDialog({ modelName, onSubmit, disabled }: BatchAnalysisDialogProps) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [prompt, setPrompt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files
    if (!selected) return
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name))
      const newFiles = Array.from(selected).filter((f) => !existing.has(f.name))
      return [...prev, ...newFiles]
    })
    // 重置 input 以便重复选择同一批文件
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [])

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const handleSubmit = async () => {
    if (files.length === 0 || !prompt.trim()) return
    setSubmitting(true)
    try {
      await onSubmit(prompt.trim(), files)
      setOpen(false)
      setFiles([])
      setPrompt('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled} title="批量文档分析">
          <FolderOpen className="size-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>批量文档分析</DialogTitle>
          <DialogDescription>
            上传多个 Word 文件（.doc 或 .docx），系统将并行调用 AI 分析每个文件并汇总结论。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 文件选择 */}
          <div className="space-y-2">
            <Label>选择文件</Label>
            <div
              className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              <FolderOpen className="size-8 mx-auto text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">
                点击选择文件，或拖拽到此处
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                支持 .doc 和 .docx 格式
              </p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".doc,.docx"
              multiple
              className="hidden"
              onChange={handleFileChange}
            />

            {/* 已选文件列表 */}
            {files.length > 0 && (
              <div className="max-h-40 overflow-y-auto space-y-1 rounded-md border p-2">
                {files.map((f, i) => (
                  <div key={`${f.name}-${i}`} className="flex items-center gap-2 text-sm">
                    <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate flex-1">{f.name}</span>
                    <Badge variant="outline" className="text-xs shrink-0">
                      {f.name.endsWith('.doc') ? 'DOC' : 'DOCX'}
                    </Badge>
                    <button
                      type="button"
                      onClick={() => removeFile(i)}
                      className="shrink-0 text-muted-foreground hover:text-foreground"
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 分析要求 */}
          <div className="space-y-2">
            <Label htmlFor="batch-prompt">分析要求</Label>
            <Textarea
              id="batch-prompt"
              placeholder="例如：分析本案的争议焦点和裁判要旨，总结竞业限制条款的效力认定标准"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
            />
          </div>

          {/* 模型信息 */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>使用模型：</span>
            <Badge variant="secondary">{modelName || '默认模型'}</Badge>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={files.length === 0 || !prompt.trim() || submitting}
          >
            {submitting ? '提交中...' : `开始分析 (${files.length} 个文件)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
