/**
 * IdentityDocList Component
 *
 * 证件列表组件
 * - 显示证件类型、文件预览、上传时间
 * - 支持图片预览
 *
 * Requirements: 4.3, 4.4
 */

import { useState, useCallback } from 'react'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { FileText, Image, Eye, Calendar } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import type { IdentityDoc } from '../types'
import { DOC_TYPE_LABELS } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface IdentityDocListProps {
  /** 证件列表 */
  docs: IdentityDoc[]
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 判断文件是否为图片
 */
function isImageFile(filePath: string): boolean {
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
  const lowerPath = filePath.toLowerCase()
  return imageExtensions.some((ext) => lowerPath.endsWith(ext))
}

/**
 * 格式化上传时间
 */
function formatUploadTime(dateString: string): string {
  try {
    const date = new Date(dateString)
    return format(date, 'yyyy年MM月dd日 HH:mm', { locale: zhCN })
  } catch {
    return dateString
  }
}

/**
 * 获取证件类型标签
 */
function getDocTypeLabel(docType: string): string {
  return DOC_TYPE_LABELS[docType as keyof typeof DOC_TYPE_LABELS] || docType
}

// ============================================================================
// Sub-components
// ============================================================================

interface DocCardProps {
  doc: IdentityDoc
  onPreview: (doc: IdentityDoc) => void
}

/**
 * 单个证件卡片组件
 */
function DocCard({ doc, onPreview }: DocCardProps) {
  const isImage = isImageFile(doc.file_path)
  const hasMediaUrl = !!doc.media_url

  return (
    <Card className="group overflow-hidden transition-shadow hover:shadow-md">
      {/* 预览区域 */}
      <div className="bg-muted/50 relative aspect-[4/3] overflow-hidden">
        {hasMediaUrl && isImage ? (
          // 图片预览
          <img
            src={doc.media_url!}
            alt={getDocTypeLabel(doc.doc_type)}
            className="size-full object-cover transition-transform group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          // 非图片或无预览 URL 时显示占位图标
          <div className="flex size-full items-center justify-center">
            {isImage ? (
              <Image className="text-muted-foreground/50 size-12" />
            ) : (
              <FileText className="text-muted-foreground/50 size-12" />
            )}
          </div>
        )}

        {/* 预览按钮悬浮层 */}
        {hasMediaUrl && isImage && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all group-hover:bg-black/40 group-hover:opacity-100">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onPreview(doc)}
              className="gap-1.5"
            >
              <Eye className="size-4" />
              预览
            </Button>
          </div>
        )}
      </div>

      {/* 信息区域 */}
      <div className="space-y-2 p-3">
        {/* 证件类型 */}
        <div className="flex items-center gap-2">
          <span className="bg-primary/10 text-primary rounded-md px-2 py-0.5 text-xs font-medium">
            {getDocTypeLabel(doc.doc_type)}
          </span>
        </div>

        {/* 上传时间 */}
        <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
          <Calendar className="size-3.5" />
          <span>{formatUploadTime(doc.uploaded_at)}</span>
        </div>
      </div>
    </Card>
  )
}

interface ImagePreviewDialogProps {
  doc: IdentityDoc | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * 图片预览对话框
 */
function ImagePreviewDialog({ doc, open, onOpenChange }: ImagePreviewDialogProps) {
  if (!doc) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-hidden p-0">
        <DialogHeader className="border-b p-4">
          <DialogTitle className="flex items-center gap-2">
            <Image className="size-5" />
            {getDocTypeLabel(doc.doc_type)}
          </DialogTitle>
        </DialogHeader>

        {/* 图片容器 */}
        <div className="bg-muted/30 flex max-h-[70vh] items-center justify-center overflow-auto p-4">
          {doc.media_url ? (
            <img
              src={doc.media_url}
              alt={getDocTypeLabel(doc.doc_type)}
              className="max-h-full max-w-full rounded-lg object-contain shadow-lg"
            />
          ) : (
            <div className="text-muted-foreground flex flex-col items-center gap-2 py-12">
              <Image className="size-16 opacity-50" />
              <span>暂无预览</span>
            </div>
          )}
        </div>

        {/* 底部信息 */}
        <div className="text-muted-foreground border-t p-4 text-sm">
          <div className="flex items-center gap-1.5">
            <Calendar className="size-4" />
            <span>上传时间：{formatUploadTime(doc.uploaded_at)}</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 证件列表组件
 *
 * Requirements:
 * - 4.3: 显示关联的身份证件列表
 * - 4.4: 显示证件类型、文件预览、上传时间
 */
export function IdentityDocList({ docs }: IdentityDocListProps) {
  // ========== 状态管理 ==========
  const [previewDoc, setPreviewDoc] = useState<IdentityDoc | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)

  // ========== 事件处理 ==========

  /**
   * 处理预览点击
   */
  const handlePreview = useCallback((doc: IdentityDoc) => {
    setPreviewDoc(doc)
    setPreviewOpen(true)
  }, [])

  /**
   * 处理预览对话框关闭
   */
  const handlePreviewOpenChange = useCallback((open: boolean) => {
    setPreviewOpen(open)
    if (!open) {
      // 延迟清除预览文档，避免关闭动画时内容闪烁
      setTimeout(() => setPreviewDoc(null), 200)
    }
  }, [])

  // ========== 渲染 ==========

  // 空状态
  if (docs.length === 0) {
    return (
      <div className="text-muted-foreground flex flex-col items-center justify-center rounded-lg border border-dashed py-12">
        <FileText className="mb-3 size-12 opacity-50" />
        <p className="text-sm">暂无证件</p>
      </div>
    )
  }

  return (
    <>
      {/* 证件网格 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {docs.map((doc, index) => (
          <DocCard
            key={`${doc.doc_type}-${doc.uploaded_at}-${index}`}
            doc={doc}
            onPreview={handlePreview}
          />
        ))}
      </div>

      {/* 图片预览对话框 */}
      <ImagePreviewDialog
        doc={previewDoc}
        open={previewOpen}
        onOpenChange={handlePreviewOpenChange}
      />
    </>
  )
}

export default IdentityDocList
