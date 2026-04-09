/**
 * IdentityDocManager - 证件管理组件（添加/删除/预览）
 */

import { useState, useCallback, useRef } from 'react'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import {
  Plus, Trash2, Eye, FileText, Image, Calendar, Upload,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import { useIdentityDocMutations } from '../hooks/use-identity-doc-mutations'
import type { ClientType, DocType, IdentityDoc } from '../types'
import { DOC_TYPE_LABELS, NATURAL_DOC_TYPES, LEGAL_DOC_TYPES } from '../types'
import { resolveMediaUrl } from '@/lib/api'

interface Props {
  clientId: string
  clientType: ClientType
  docs: IdentityDoc[]
}

function isImageFile(path: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(path)
}

export function IdentityDocManager({ clientId, clientType, docs }: Props) {
  const { addDoc, deleteDoc } = useIdentityDocMutations(clientId)

  const [previewDoc, setPreviewDoc] = useState<IdentityDoc | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [deleteIdx, setDeleteIdx] = useState<number | null>(null)
  const [newDocType, setNewDocType] = useState<DocType>('id_card')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const availableDocTypes = clientType === 'natural' ? NATURAL_DOC_TYPES : LEGAL_DOC_TYPES

  const handleAdd = useCallback(async () => {
    if (!selectedFile) { toast.error('请选择文件'); return }
    try {
      await addDoc.mutateAsync({ docType: newDocType, file: selectedFile })
      toast.success('证件已添加')
      setAddOpen(false)
      setSelectedFile(null)
    } catch {
      toast.error('添加失败')
    }
  }, [addDoc, newDocType, selectedFile])

  const handleDelete = useCallback(async () => {
    // 后端 identity-docs 删除需要 doc_id，但当前 IdentityDoc 没有 id
    // 需要通过 getIdentityDoc 或者后端返回 id。暂时用 index 标识
    // 实际上后端 delete 需要 doc_id，这里我们需要先获取
    if (deleteIdx === null) return
    const doc = docs[deleteIdx]
    if (!doc) return
    // 由于当前 IdentityDoc 没有 id，我们需要通过 API 获取
    // 暂时提示用户在 admin 后台删除
    toast.info('证件删除功能需要后端返回证件 ID，请在后台管理中操作')
    setDeleteIdx(null)
  }, [deleteIdx, docs])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-sm">
          共 {docs.length} 份证件
        </p>
        <Button size="sm" onClick={() => { setNewDocType(availableDocTypes[0]); setAddOpen(true) }}>
          <Plus className="mr-1.5 size-4" />添加证件
        </Button>
      </div>

      {docs.length === 0 ? (
        <div className="text-muted-foreground flex flex-col items-center justify-center rounded-lg border border-dashed py-16">
          <FileText className="mb-3 size-12 opacity-40" />
          <p className="text-sm">暂无证件</p>
          <p className="mt-1 text-xs opacity-60">点击「添加证件」上传</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {docs.map((doc, idx) => {
            const mediaUrl = resolveMediaUrl(doc.media_url)
            const isImg = isImageFile(doc.file_path) || (doc.media_url ? isImageFile(doc.media_url) : false)
            return (
              <Card key={`${doc.doc_type}-${idx}`} className="group overflow-hidden transition-shadow hover:shadow-md">
                {/* 预览区 */}
                <div className="bg-muted/50 relative aspect-[4/3] overflow-hidden">
                  {mediaUrl && isImg ? (
                    <img
                      src={mediaUrl}
                      alt={DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                      className="size-full object-cover transition-transform group-hover:scale-105"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex size-full items-center justify-center">
                      {isImg ? <Image className="text-muted-foreground/40 size-12" /> : <FileText className="text-muted-foreground/40 size-12" />}
                    </div>
                  )}
                  {/* 悬浮操作 */}
                  <div className="absolute inset-0 flex items-center justify-center gap-2 bg-black/0 opacity-0 transition-all group-hover:bg-black/40 group-hover:opacity-100">
                    {mediaUrl && isImg && (
                      <Button variant="secondary" size="sm" onClick={() => setPreviewDoc(doc)}>
                        <Eye className="mr-1 size-3.5" />预览
                      </Button>
                    )}
                    {mediaUrl && !isImg && (
                      <Button variant="secondary" size="sm" asChild>
                        <a href={mediaUrl} target="_blank" rel="noopener noreferrer">
                          <Eye className="mr-1 size-3.5" />查看
                        </a>
                      </Button>
                    )}
                    {mediaUrl && (
                      <Button variant="secondary" size="sm" asChild>
                        <a href={mediaUrl} download>
                          <FileText className="mr-1 size-3.5" />下载
                        </a>
                      </Button>
                    )}
                    <Button variant="destructive" size="sm" onClick={() => setDeleteIdx(idx)}>
                      <Trash2 className="mr-1 size-3.5" />删除
                    </Button>
                  </div>
                </div>
                {/* 信息 */}
                <div className="space-y-1.5 p-3">
                  <span className="bg-primary/10 text-primary rounded-md px-2 py-0.5 text-xs font-medium">
                    {DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                  </span>
                  <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                    <Calendar className="size-3.5" />
                    {format(new Date(doc.uploaded_at), 'yyyy年MM月dd日 HH:mm', { locale: zhCN })}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* 图片预览 */}
      <Dialog open={!!previewDoc} onOpenChange={(open) => !open && setPreviewDoc(null)}>
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-hidden p-0">
          <DialogHeader className="border-b p-4">
            <DialogTitle className="flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Image className="size-5" />
                {previewDoc && (DOC_TYPE_LABELS[previewDoc.doc_type] || previewDoc.doc_type)}
              </span>
              {previewDoc?.media_url && (
                <a
                  href={resolveMediaUrl(previewDoc.media_url)!}
                  download
                  className="text-primary text-sm font-normal hover:underline"
                >
                  下载原图
                </a>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="bg-muted/30 flex max-h-[70vh] items-center justify-center overflow-auto p-4">
            {previewDoc?.media_url && (
              <img src={resolveMediaUrl(previewDoc.media_url)!} alt="" className="max-h-full max-w-full rounded-lg object-contain shadow-lg" />
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* 添加证件对话框 */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>添加证件</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>证件类型</Label>
              <Select value={newDocType} onValueChange={(v) => setNewDocType(v as DocType)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {availableDocTypes.map((dt) => (
                    <SelectItem key={dt} value={dt}>{DOC_TYPE_LABELS[dt]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>选择文件</Label>
              <Input
                ref={fileRef}
                type="file"
                accept=".jpg,.jpeg,.png,.pdf"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              />
            </div>
            {selectedFile && (
              <div className="bg-muted/50 flex items-center gap-2 rounded px-3 py-2 text-sm">
                <Upload className="size-4" />
                {selectedFile.name}
                <span className="text-muted-foreground text-xs">
                  ({(selectedFile.size / 1024).toFixed(0)} KB)
                </span>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>取消</Button>
            <Button onClick={handleAdd} disabled={addDoc.isPending || !selectedFile}>
              {addDoc.isPending ? '上传中...' : '上传'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <AlertDialog open={deleteIdx !== null} onOpenChange={(open) => !open && setDeleteIdx(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>删除后无法恢复，确定要删除这份证件吗？</AlertDialogDescription>
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
