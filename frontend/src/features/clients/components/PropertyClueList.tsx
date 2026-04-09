/**
 * PropertyClueList - 财产线索列表组件
 */

import { useState, useCallback, useRef } from 'react'
import {
  Plus, Trash2, Edit, Paperclip, Upload, FileText, ChevronDown, ChevronUp,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'

import { usePropertyClues } from '../hooks/use-property-clues'
import { usePropertyClueMutations } from '../hooks/use-property-clue-mutations'
import { PropertyClueFormDialog } from './PropertyClueFormDialog'
import type { PropertyClue } from '../types'
import { CLUE_TYPE_LABELS, type ClueType } from '../types'
import { resolveMediaUrl } from '@/lib/api'

interface Props {
  clientId: number
}

const CLUE_TYPE_COLORS: Record<ClueType, string> = {
  bank: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  alipay: 'bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200',
  wechat: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  real_estate: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  other: 'bg-gray-100 text-gray-800 dark:bg-muted dark:text-muted-foreground',
}

export function PropertyClueList({ clientId }: Props) {
  const { data: clues = [], isLoading } = usePropertyClues(clientId)
  const { deleteClue, uploadAttachment, deleteAttachment } = usePropertyClueMutations(clientId)

  const [formOpen, setFormOpen] = useState(false)
  const [editingClue, setEditingClue] = useState<PropertyClue | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null)
  const [collapsedIds, setCollapsedIds] = useState<Set<number>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadClueId, setUploadClueId] = useState<number | null>(null)

  const toggleExpand = useCallback((id: number) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const handleDelete = useCallback(async () => {
    if (deleteTarget === null) return
    try {
      await deleteClue.mutateAsync(deleteTarget)
      toast.success('线索已删除')
    } catch {
      toast.error('删除失败')
    }
    setDeleteTarget(null)
  }, [deleteTarget, deleteClue])

  const handleUploadClick = useCallback((clueId: number) => {
    setUploadClueId(clueId)
    fileInputRef.current?.click()
  }, [])

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || uploadClueId === null) return
    try {
      await uploadAttachment.mutateAsync({ clueId: uploadClueId, file })
      toast.success('附件已上传')
    } catch {
      toast.error('上传失败')
    }
    e.target.value = ''
    setUploadClueId(null)
  }, [uploadClueId, uploadAttachment])

  const handleDeleteAttachment = useCallback(async (attachmentId: number) => {
    try {
      await deleteAttachment.mutateAsync(attachmentId)
      toast.success('附件已删除')
    } catch {
      toast.error('删除失败')
    }
  }, [deleteAttachment])

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="bg-muted h-24 animate-pulse rounded-lg" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-sm">
          共 {clues.length} 条财产线索
        </p>
        <Button size="sm" onClick={() => { setEditingClue(null); setFormOpen(true) }}>
          <Plus className="mr-1.5 size-4" />新建线索
        </Button>
      </div>

      {clues.length === 0 ? (
        <div className="text-muted-foreground flex flex-col items-center justify-center rounded-lg border border-dashed py-16">
          <FileText className="mb-3 size-12 opacity-40" />
          <p className="text-sm">暂无财产线索</p>
          <p className="mt-1 text-xs opacity-60">点击「新建线索」添加</p>
        </div>
      ) : (
        <div className="space-y-3">
          {clues.map((clue) => {
            const expanded = !collapsedIds.has(clue.id)
            return (
              <Card key={clue.id} className="overflow-hidden transition-shadow hover:shadow-md">
                <CardContent className="p-4">
                  {/* 头部 */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-2 flex items-center gap-2">
                        <Badge variant="secondary" className={CLUE_TYPE_COLORS[clue.clue_type as ClueType] || ''}>
                          {CLUE_TYPE_LABELS[clue.clue_type as ClueType] || clue.clue_type}
                        </Badge>
                        {clue.attachments.length > 0 && (
                          <span className="text-muted-foreground flex items-center gap-1 text-xs">
                            <Paperclip className="size-3" />{clue.attachments.length}
                          </span>
                        )}
                      </div>
                      <pre className="text-foreground/80 max-h-20 overflow-hidden whitespace-pre-wrap font-sans text-sm leading-relaxed">
                        {clue.content || '（无内容）'}
                      </pre>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button variant="ghost" size="icon" className="size-8" onClick={() => { setEditingClue(clue); setFormOpen(true) }}>
                        <Edit className="size-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="size-8" onClick={() => handleUploadClick(clue.id)}>
                        <Upload className="size-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="text-destructive size-8" onClick={() => setDeleteTarget(clue.id)}>
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </div>

                  {/* 附件折叠区 */}
                  {clue.attachments.length > 0 && (
                    <div className="mt-3 border-t pt-3">
                      <button
                        type="button"
                        className="text-muted-foreground flex items-center gap-1 text-xs hover:underline"
                        onClick={() => toggleExpand(clue.id)}
                      >
                        {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                        {clue.attachments.length} 个附件
                      </button>
                      {expanded && (
                        <div className="mt-2 space-y-1.5">
                          {clue.attachments.map((att) => (
                            <div key={att.id} className="bg-muted/50 flex items-center justify-between rounded px-3 py-2">
                              <a
                                href={resolveMediaUrl(att.media_url) || '#'}
                                target="_blank"
                                rel="noopener noreferrer"
                                download={att.file_name}
                                className="text-primary flex items-center gap-1.5 text-xs hover:underline"
                              >
                                <Paperclip className="size-3" />{att.file_name}
                              </a>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="text-destructive size-6"
                                onClick={() => handleDeleteAttachment(att.id)}
                              >
                                <Trash2 className="size-3" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* 时间 */}
                  <p className="text-muted-foreground mt-2 text-xs">
                    创建于 {new Date(clue.created_at).toLocaleDateString('zh-CN')}
                  </p>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* 隐藏文件输入 */}
      <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileChange} />

      {/* 新建/编辑对话框 */}
      <PropertyClueFormDialog
        clientId={clientId}
        clue={editingClue}
        open={formOpen}
        onOpenChange={setFormOpen}
      />

      {/* 删除确认 */}
      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>删除后无法恢复，确定要删除这条财产线索吗？</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
