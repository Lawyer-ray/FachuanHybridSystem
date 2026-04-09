/**
 * FileUploader Component
 *
 * 文件上传组件 - 用于文书智能识别
 * - 支持拖拽和点击上传
 * - 实现文件类型和大小验证
 * - 显示上传进度
 * - 显示错误提示
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 6.7, 6.8
 */

import { useCallback, useState, useRef } from 'react'
import {
  Upload,
  FileImage,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  X,
  AlertCircle,
  RefreshCw,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'

import { useUploadDocument } from '../hooks/use-recognition-mutations'
import { FILE_ERRORS } from '../schemas'
import { ACCEPTED_FILE_TYPES, MAX_FILE_SIZE } from '../../constants'
import type { DocumentRecognitionTask } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface FileUploaderProps {
  /** 上传成功回调 */
  onUploadSuccess: (task: DocumentRecognitionTask) => void
  /** 上传失败回调 */
  onUploadError?: (error: Error) => void
  /** 允许的文件类型（可选，默认使用常量） */
  acceptedTypes?: string[]
  /** 最大文件大小（字节，可选，默认使用常量） */
  maxSize?: number
}

/** 上传状态 */
type UploadStatus = 'idle' | 'validating' | 'uploading' | 'success' | 'error'

/** 支持的文件扩展名 */
const ACCEPTED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 获取文件图标
 */
function getFileIcon(file: File) {
  if (file.type === 'application/pdf') {
    return FileText
  }
  return FileImage
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * 获取文件类型显示名称
 */
function getFileTypeName(mimeType: string): string {
  const typeMap: Record<string, string> = {
    'application/pdf': 'PDF',
    'image/jpeg': 'JPG',
    'image/png': 'PNG',
  }
  return typeMap[mimeType] || '未知'
}

// ============================================================================
// Sub-components
// ============================================================================

interface DropZoneProps {
  isDragging: boolean
  isUploading: boolean
  onDragEnter: (e: React.DragEvent) => void
  onDragLeave: (e: React.DragEvent) => void
  onDragOver: (e: React.DragEvent) => void
  onDrop: (e: React.DragEvent) => void
  onClick: () => void
}

/**
 * 拖拽上传区域
 * Requirements: 6.1 - 提供文件上传区域，支持拖拽和点击上传
 */
function DropZone({
  isDragging,
  isUploading,
  onDragEnter,
  onDragLeave,
  onDragOver,
  onDrop,
  onClick,
}: DropZoneProps) {
  return (
    <div
      className={`
        relative flex min-h-[200px] cursor-pointer flex-col items-center justify-center
        rounded-lg border-2 border-dashed p-6 transition-all duration-200
        ${
          isDragging
            ? 'border-primary bg-primary/5 scale-[1.02]'
            : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50'
        }
        ${isUploading ? 'pointer-events-none opacity-60' : ''}
      `}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      aria-label="上传法律文书进行智能识别"
    >
      {isUploading ? (
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="text-primary size-12 animate-spin" />
          <p className="text-muted-foreground text-sm">正在上传中...</p>
        </div>
      ) : (
        <>
          <div
            className={`
              mb-4 rounded-full p-4 transition-colors
              ${isDragging ? 'bg-primary/10' : 'bg-muted'}
            `}
          >
            <Upload
              className={`size-8 ${isDragging ? 'text-primary' : 'text-muted-foreground'}`}
            />
          </div>
          <p className="text-foreground mb-1 text-center font-medium">
            {isDragging ? '松开鼠标上传文件' : '拖拽文件到此处上传'}
          </p>
          <p className="text-muted-foreground mb-3 text-center text-sm">
            或点击选择文件
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <Badge variant="secondary" className="text-xs">
              PDF
            </Badge>
            <Badge variant="secondary" className="text-xs">
              JPG
            </Badge>
            <Badge variant="secondary" className="text-xs">
              PNG
            </Badge>
          </div>
          <p className="text-muted-foreground mt-2 text-xs">
            支持法律文书，最大 10MB
          </p>
        </>
      )}
    </div>
  )
}

interface FilePreviewProps {
  file: File
  status: UploadStatus
  progress: number
  errorMessage?: string
  onRemove: () => void
  onRetry: () => void
}

/**
 * 文件预览组件
 * Requirements: 6.4 - 显示文件预览和上传进度
 */
function FilePreview({
  file,
  status,
  progress,
  errorMessage,
  onRemove,
  onRetry,
}: FilePreviewProps) {
  const FileIcon = getFileIcon(file)

  return (
    <div className="bg-muted/50 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-3">
        <div className="bg-background flex size-10 items-center justify-center rounded-lg shrink-0">
          <FileIcon className="text-muted-foreground size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{file.name}</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{formatFileSize(file.size)}</span>
            <span>•</span>
            <span>{getFileTypeName(file.type)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status === 'uploading' && (
            <Loader2 className="text-primary size-5 animate-spin" />
          )}
          {status === 'success' && <CheckCircle2 className="size-5 text-green-500" />}
          {status === 'error' && (
            <>
              <XCircle className="size-5 text-red-500" />
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={(e) => {
                  e.stopPropagation()
                  onRetry()
                }}
                aria-label="重试上传"
                title="重试上传"
              >
                <RefreshCw className="size-4" />
              </Button>
            </>
          )}
          {status !== 'uploading' && (
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={(e) => {
                e.stopPropagation()
                onRemove()
              }}
              aria-label="移除文件"
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
      </div>

      {/* 上传进度条 - Requirements: 6.4 */}
      {status === 'uploading' && (
        <div className="space-y-1">
          <Progress value={progress} className="h-2" />
          <p className="text-xs text-muted-foreground text-right">{progress}%</p>
        </div>
      )}

      {/* 错误信息 - Requirements: 6.6, 6.7, 6.8 */}
      {status === 'error' && errorMessage && (
        <div className="flex items-start gap-2 p-2 rounded-md bg-destructive/10 text-destructive">
          <AlertCircle className="size-4 mt-0.5 shrink-0" />
          <p className="text-xs">{errorMessage}</p>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 文件上传组件
 *
 * Requirements:
 * - 6.1: 提供文件上传区域，支持拖拽和点击上传
 * - 6.2: 限制上传文件类型为 PDF、图片（jpg/png）
 * - 6.3: 限制单个文件大小不超过 10MB
 * - 6.4: 显示文件预览和上传进度
 * - 6.6: 文件格式不支持时显示格式错误提示
 * - 6.7: 文件过大时显示大小限制提示
 * - 6.8: 上传失败时显示错误提示并允许重试
 */
export function FileUploader({
  onUploadSuccess,
  onUploadError,
  acceptedTypes = [...ACCEPTED_FILE_TYPES],
  maxSize = MAX_FILE_SIZE,
}: FileUploaderProps) {
  // ========== State ==========
  const [isDragging, setIsDragging] = useState(false)
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [errorMessage, setErrorMessage] = useState<string | undefined>()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounterRef = useRef(0)

  // ========== Hooks ==========
  const uploadDocument = useUploadDocument()

  // ========== File Validation ==========

  /**
   * 验证文件
   * Requirements: 6.2, 6.3
   */
  const validateFile = useCallback(
    (file: File): { valid: boolean; error?: string } => {
      // 验证文件类型 - Requirements: 6.2
      // 使用自定义 acceptedTypes 或默认验证
      const isValidType = acceptedTypes.includes(file.type)
      if (!isValidType) {
        return {
          valid: false,
          error: FILE_ERRORS.INVALID_TYPE,
        }
      }

      // 验证文件大小 - Requirements: 6.3
      // 使用自定义 maxSize 或默认验证
      const isValidSize = file.size <= maxSize
      if (!isValidSize) {
        return {
          valid: false,
          error: FILE_ERRORS.FILE_TOO_LARGE,
        }
      }

      return { valid: true }
    },
    [acceptedTypes, maxSize]
  )

  /**
   * 处理文件上传
   */
  const handleUpload = useCallback(
    async (file: File) => {
      setSelectedFile(file)
      setStatus('validating')
      setErrorMessage(undefined)
      setUploadProgress(0)

      // 验证文件
      const validation = validateFile(file)
      if (!validation.valid) {
        setStatus('error')
        setErrorMessage(validation.error)
        toast.error(validation.error)
        onUploadError?.(new Error(validation.error))
        return
      }

      // 开始上传
      setStatus('uploading')

      // 模拟上传进度（因为实际上传是通过 mutation 完成的）
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval)
            return 90
          }
          return prev + 10
        })
      }, 200)

      try {
        const task = await uploadDocument.mutateAsync(file)
        clearInterval(progressInterval)
        setUploadProgress(100)
        setStatus('success')
        onUploadSuccess(task)
      } catch (error) {
        clearInterval(progressInterval)
        setStatus('error')
        const errorMsg =
          error instanceof Error ? error.message : FILE_ERRORS.UPLOAD_FAILED
        setErrorMessage(errorMsg)
        onUploadError?.(error instanceof Error ? error : new Error(errorMsg))
      }
    },
    [validateFile, uploadDocument, onUploadSuccess, onUploadError]
  )

  /**
   * 处理重试上传
   * Requirements: 6.8 - 允许重试
   */
  const handleRetry = useCallback(() => {
    if (selectedFile) {
      handleUpload(selectedFile)
    }
  }, [selectedFile, handleUpload])

  // ========== Event Handlers ==========

  /**
   * 处理拖拽进入
   */
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current++
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true)
    }
  }, [])

  /**
   * 处理拖拽离开
   */
  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current--
    if (dragCounterRef.current === 0) {
      setIsDragging(false)
    }
  }, [])

  /**
   * 处理拖拽悬停
   */
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  /**
   * 处理文件拖放
   * Requirements: 6.1 - 支持拖拽上传
   */
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
      dragCounterRef.current = 0

      const files = e.dataTransfer.files
      if (files && files.length > 0) {
        handleUpload(files[0])
      }
    },
    [handleUpload]
  )

  /**
   * 处理点击上传
   * Requirements: 6.1 - 支持点击上传
   */
  const handleClick = useCallback(() => {
    if (status !== 'uploading') {
      fileInputRef.current?.click()
    }
  }, [status])

  /**
   * 处理文件选择
   */
  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files && files.length > 0) {
        handleUpload(files[0])
      }
      // 重置 input 以允许重复选择同一文件
      e.target.value = ''
    },
    [handleUpload]
  )

  /**
   * 处理移除文件
   */
  const handleRemoveFile = useCallback(() => {
    setSelectedFile(null)
    setStatus('idle')
    setErrorMessage(undefined)
    setUploadProgress(0)
  }, [])

  // ========== Render ==========

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">上传文书</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 隐藏的文件输入 */}
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          onChange={handleFileChange}
          className="hidden"
          aria-hidden="true"
        />

        {/* 拖拽上传区域 - Requirements: 6.1 */}
        {!selectedFile && (
          <DropZone
            isDragging={isDragging}
            isUploading={status === 'uploading'}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={handleClick}
          />
        )}

        {/* 文件预览 - Requirements: 6.4 */}
        {selectedFile && (
          <FilePreview
            file={selectedFile}
            status={status}
            progress={uploadProgress}
            errorMessage={errorMessage}
            onRemove={handleRemoveFile}
            onRetry={handleRetry}
          />
        )}

        {/* 提示信息 */}
        <p className="text-muted-foreground text-xs">
          上传法律文书（判决书、裁定书等），系统将自动识别文书类型、案号等信息并尝试绑定案件。
        </p>
      </CardContent>
    </Card>
  )
}

export default FileUploader
