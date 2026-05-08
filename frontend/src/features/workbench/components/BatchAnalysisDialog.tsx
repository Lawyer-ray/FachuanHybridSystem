/* eslint-disable react-refresh/only-export-components */
import { useState, useRef, useCallback } from 'react'
import { FolderOpen, X, FileText, Upload } from 'lucide-react'

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

const SUPPORTED_EXTS = new Set(['.doc', '.docx', '.xls', '.xlsx'])

/** 递归读取目录中的支持格式文件 */
async function readDirectoryEntries(dirEntry: FileSystemDirectoryEntry): Promise<File[]> {
  const reader = dirEntry.createReader()
  const allFiles: File[] = []

  // createReader.readEntries 可能分批返回，需循环读取
  const readBatch = (): Promise<FileSystemEntry[]> =>
    new Promise((resolve, reject) => reader.readEntries(resolve, reject))

  let entries: FileSystemEntry[]
  do {
    entries = await readBatch()
    for (const entry of entries) {
      if (entry.isFile) {
        const ext = entry.name.toLowerCase().slice(entry.name.lastIndexOf('.'))
        if (SUPPORTED_EXTS.has(ext)) {
          const file = await new Promise<File>((resolve, reject) =>
            (entry as FileSystemFileEntry).file(resolve, reject),
          )
          allFiles.push(file)
        }
      } else if (entry.isDirectory) {
        const sub = await readDirectoryEntries(entry as FileSystemDirectoryEntry)
        allFiles.push(...sub)
      }
    }
  } while (entries.length > 0)

  return allFiles
}

export function BatchAnalysisDialog({ modelName, onSubmit, disabled }: BatchAnalysisDialogProps) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [prompt, setPrompt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const addFiles = useCallback((newFiles: File[]) => {
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name))
      const unique = newFiles.filter((f) => !existing.has(f.name))
      return [...prev, ...unique]
    })
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files
    if (!selected) return
    addFiles(Array.from(selected))
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [addFiles])

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragging(false)

    const items = e.dataTransfer.items
    if (!items?.length) return

    const collected: File[] = []
    const promises: Promise<void>[] = []

    for (const item of Array.from(items)) {
      const entry = item.webkitGetAsEntry?.()
      if (!entry) continue

      if (entry.isFile) {
        const ext = entry.name.toLowerCase().slice(entry.name.lastIndexOf('.'))
        if (SUPPORTED_EXTS.has(ext)) {
          promises.push(
            new Promise<void>((resolve, reject) => {
              (entry as FileSystemFileEntry).file(
                (file) => { collected.push(file); resolve() },
                reject,
              )
            }),
          )
        }
      } else if (entry.isDirectory) {
        promises.push(
          readDirectoryEntries(entry as FileSystemDirectoryEntry).then((files) => {
            collected.push(...files)
          }),
        )
      }
    }

    await Promise.all(promises)
    if (collected.length > 0) addFiles(collected)
  }, [addFiles])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragging(false)
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
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>批量文档分析</DialogTitle>
          <DialogDescription>
            上传 Word 文件（.doc/.docx）或 Excel 文件（.xls/.xlsx），系统将并行调用 AI 分析每个文件/每行数据并汇总结论。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto px-1">
          {/* 文件选择 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>选择文件</Label>
              {files.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => fileInputRef.current?.click()}
                >
                  继续添加
                </Button>
              )}
            </div>

            {/* 未选文件时显示 drop zone，已选文件时折叠为紧凑样式 */}
            {files.length === 0 ? (
              <div
                className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                  dragging ? 'border-primary bg-primary/5' : 'hover:border-primary/50'
                }`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                {dragging ? (
                  <Upload className="size-8 mx-auto text-primary mb-2" />
                ) : (
                  <FolderOpen className="size-8 mx-auto text-muted-foreground mb-2" />
                )}
                <p className="text-sm text-muted-foreground">
                  点击选择文件，或拖拽文件/文件夹到此处
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  支持 .doc、.docx、.xls、.xlsx 格式，Excel 按行拆分，拖入文件夹会自动提取
                </p>
              </div>
            ) : (
              <div
                className={`rounded-md border transition-colors ${dragging ? 'border-primary bg-primary/5' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <div className="max-h-40 overflow-y-auto divide-y">
                  {files.map((f, i) => (
                    <div key={`${f.name}-${i}`} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                      <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate flex-1">{f.name}</span>
                      <Badge variant="outline" className="text-xs shrink-0">
                        {f.name.split('.').pop()?.toUpperCase() || 'FILE'}
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
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".doc,.docx,.xls,.xlsx"
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
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
