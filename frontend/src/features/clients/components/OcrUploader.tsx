/**
 * OcrUploader Component
 *
 * OCR 上传组件
 * - 实现拖拽上传和点击选择
 * - 支持 JPG、PNG、PDF 格式验证
 * - 调用 OCR 识别 API
 * - 显示识别结果和加载状态
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8, 6.9
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
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

import { clientApi } from '../api'
import type { OcrResult, OcrRecognizeResult, ClientType } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface OcrUploaderProps {
  /** OCR 识别成功回调 */
  onRecognized: (data: OcrResult) => void
  /** OCR 识别失败回调 */
  onError: (error: string) => void
}

/** 上传状态 */
type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'

/** 支持的文件类型 */
const ACCEPTED_FILE_TYPES = [
  'image/jpeg',
  'image/jpg',
  'image/png',
  'application/pdf',
]

/** 支持的文件扩展名 */
const ACCEPTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf']

/** 最大文件大小 (10MB) */
const MAX_FILE_SIZE = 10 * 1024 * 1024

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 验证文件类型
 * Requirements: 6.3
 */
function isValidFileType(file: File): boolean {
  // 检查 MIME 类型
  if (ACCEPTED_FILE_TYPES.includes(file.type)) {
    return true
  }

  // 检查文件扩展名（作为后备）
  const fileName = file.name.toLowerCase()
  return ACCEPTED_EXTENSIONS.some((ext) => fileName.endsWith(ext))
}

/**
 * 验证文件大小
 */
function isValidFileSize(file: File): boolean {
  return file.size <= MAX_FILE_SIZE
}

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
 * 根据识别结果推断当事人类型
 */
function inferClientType(data: OcrResult): ClientType {
  // 如果有法定代表人信息，说明是法人或非法人组织
  if (data.legal_representative) {
    return 'legal'
  }
  // 默认为自然人
  return 'natural'
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
 * Requirements: 6.1, 6.2
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
      aria-label="上传身份证或营业执照图片"
    >
      {isUploading ? (
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="text-primary size-12 animate-spin" />
          <p className="text-muted-foreground text-sm">正在识别中...</p>
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
              JPG
            </Badge>
            <Badge variant="secondary" className="text-xs">
              PNG
            </Badge>
            <Badge variant="secondary" className="text-xs">
              PDF
            </Badge>
          </div>
          <p className="text-muted-foreground mt-2 text-xs">
            支持身份证、营业执照，最大 10MB
          </p>
        </>
      )}
    </div>
  )
}

interface FilePreviewProps {
  file: File
  status: UploadStatus
  onRemove: () => void
}

/**
 * 文件预览组件
 */
function FilePreview({ file, status, onRemove }: FilePreviewProps) {
  const FileIcon = getFileIcon(file)

  return (
    <div className="bg-muted/50 flex items-center gap-3 rounded-lg p-3">
      <div className="bg-background flex size-10 items-center justify-center rounded-lg">
        <FileIcon className="text-muted-foreground size-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{file.name}</p>
        <p className="text-muted-foreground text-xs">{formatFileSize(file.size)}</p>
      </div>
      <div className="flex items-center gap-2">
        {status === 'uploading' && (
          <Loader2 className="text-primary size-5 animate-spin" />
        )}
        {status === 'success' && <CheckCircle2 className="size-5 text-green-500" />}
        {status === 'error' && <XCircle className="size-5 text-red-500" />}
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
  )
}

interface RecognitionResultProps {
  result: OcrResult
  onConfirm: () => void
  onCancel: () => void
}

/**
 * 识别结果展示组件
 * Requirements: 6.7
 */
function RecognitionResult({ result, onConfirm, onCancel }: RecognitionResultProps) {
  const hasData =
    result.name || result.id_number || result.address || result.legal_representative

  if (!hasData) {
    return (
      <div className="bg-muted/50 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 size-5 text-amber-500" />
          <div>
            <p className="font-medium">未能识别到有效信息</p>
            <p className="text-muted-foreground mt-1 text-sm">
              请确保图片清晰，或尝试手动输入信息
            </p>
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <Button variant="outline" size="sm" onClick={onCancel}>
            关闭
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="size-5 text-green-500" />
        <span className="font-medium">识别成功</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {result.name && (
          <div className="space-y-1">
            <p className="text-muted-foreground text-xs">姓名/公司名称</p>
            <p className="text-sm font-medium">{result.name}</p>
          </div>
        )}
        {result.id_number && (
          <div className="space-y-1">
            <p className="text-muted-foreground text-xs">身份证号/统一社会信用代码</p>
            <p className="text-sm font-medium">{result.id_number}</p>
          </div>
        )}
        {result.address && (
          <div className="col-span-full space-y-1">
            <p className="text-muted-foreground text-xs">地址</p>
            <p className="text-sm font-medium">{result.address}</p>
          </div>
        )}
        {result.legal_representative && (
          <div className="space-y-1">
            <p className="text-muted-foreground text-xs">法定代表人</p>
            <p className="text-sm font-medium">{result.legal_representative}</p>
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          取消
        </Button>
        <Button size="sm" onClick={onConfirm}>
          确认填充
        </Button>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * OCR 上传组件
 *
 * Requirements:
 * - 6.1: 提供文件上传区域支持上传身份证/营业执照图片
 * - 6.2: 支持拖拽上传和点击选择文件
 * - 6.3: 支持 JPG、PNG、PDF 格式的文件
 * - 6.4: 上传身份证图片时调用 OCR 识别接口提取姓名、身份证号、地址
 * - 6.5: 上传营业执照图片时调用 OCR 识别接口提取公司名称、统一社会信用代码、法定代表人、地址
 * - 6.7: OCR 识别成功时显示识别结果供用户确认或修改
 * - 6.8: OCR 识别失败时显示错误提示并允许用户手动输入
 * - 6.9: OCR 识别过程中显示加载状态
 */
export function OcrUploader({ onRecognized, onError }: OcrUploaderProps) {
  // ========== State ==========
  const [isDragging, setIsDragging] = useState(false)
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [recognitionResult, setRecognitionResult] = useState<OcrResult | null>(null)
  const [useAsync, setUseAsync] = useState(false)
  const [taskProgress, setTaskProgress] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounterRef = useRef(0)

  // ========== File Validation ==========

  /**
   * 验证并处理文件
   */
  const validateAndProcessFile = useCallback(
    async (file: File) => {
      // 验证文件类型 - Requirements: 6.3
      if (!isValidFileType(file)) {
        const errorMsg = '不支持的文件格式，请上传 JPG、PNG 或 PDF 文件'
        toast.error(errorMsg)
        onError(errorMsg)
        return
      }

      // 验证文件大小
      if (!isValidFileSize(file)) {
        const errorMsg = '文件大小超过限制，最大支持 10MB'
        toast.error(errorMsg)
        onError(errorMsg)
        return
      }

      setSelectedFile(file)
      setStatus('uploading')
      setRecognitionResult(null)

      try {
        if (useAsync) {
          // 异步模式：提交任务并轮询
          setTaskProgress('正在提交识别任务...')
          const submitRes = await clientApi.submitRecognizeTask(file)
          setTaskProgress('任务已提交，正在处理...')
          toast.info('识别任务已提交，请等待结果')

          // 轮询任务状态
          const pollResult = await new Promise<OcrRecognizeResult>((resolve, reject) => {
            let attempts = 0
            const maxAttempts = 60 // 最多轮询 60 次（5 分钟）
            const poll = async () => {
              attempts++
              if (attempts > maxAttempts) {
                reject(new Error('识别超时，请重试'))
                return
              }
              try {
                const statusRes = await clientApi.getRecognizeTaskStatus(submitRes.task_id)
                if (statusRes.status === 'completed' && statusRes.result) {
                  resolve(statusRes.result)
                } else if (statusRes.status === 'failed') {
                  reject(new Error('识别任务失败'))
                } else {
                  setTaskProgress(`处理中... (${attempts}/${maxAttempts})`)
                  setTimeout(poll, 5000)
                }
              } catch {
                reject(new Error('查询任务状态失败'))
              }
            }
            poll()
          })

          if (pollResult.success && pollResult.extracted_data) {
            const ocrResult: OcrResult = {
              name: pollResult.extracted_data.name,
              id_number: pollResult.extracted_data.id_number,
              address: pollResult.extracted_data.address,
              legal_representative: pollResult.extracted_data.legal_representative,
              client_type: inferClientType(pollResult.extracted_data as OcrResult),
            }
            setRecognitionResult(ocrResult)
            setStatus('success')
            toast.success('识别成功，请确认识别结果')
          } else {
            setStatus('error')
            toast.error(pollResult.error || '识别失败')
            onError(pollResult.error || '识别失败')
          }
          setTaskProgress(null)
        } else {
          // 同步模式
          const result = await clientApi.recognizeIdentityDoc(file)

          if (result.success && result.extracted_data) {
            const ocrResult: OcrResult = {
              name: result.extracted_data.name,
              id_number: result.extracted_data.id_number,
              address: result.extracted_data.address,
              legal_representative: result.extracted_data.legal_representative,
              client_type: inferClientType(result.extracted_data as OcrResult),
            }
            setRecognitionResult(ocrResult)
            setStatus('success')
            toast.success('识别成功，请确认识别结果')
          } else {
            const errorMsg = result.error || '识别失败，请重试或手动输入'
            setStatus('error')
            toast.error(errorMsg)
            onError(errorMsg)
          }
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : '识别失败，请检查网络连接'
        setStatus('error')
        toast.error(errorMsg)
        onError(errorMsg)
        setTaskProgress(null)
      }
    },
    [onError, useAsync]
  )

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
   * Requirements: 6.2
   */
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
      dragCounterRef.current = 0

      const files = e.dataTransfer.files
      if (files && files.length > 0) {
        validateAndProcessFile(files[0])
      }
    },
    [validateAndProcessFile]
  )

  /**
   * 处理点击上传
   * Requirements: 6.2
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
        validateAndProcessFile(files[0])
      }
      // 重置 input 以允许重复选择同一文件
      e.target.value = ''
    },
    [validateAndProcessFile]
  )

  /**
   * 处理移除文件
   */
  const handleRemoveFile = useCallback(() => {
    setSelectedFile(null)
    setStatus('idle')
    setRecognitionResult(null)
  }, [])

  /**
   * 处理确认识别结果
   * Requirements: 6.7
   */
  const handleConfirmResult = useCallback(() => {
    if (recognitionResult) {
      onRecognized(recognitionResult)
      toast.success('已填充识别结果到表单')
      // 保留文件预览，但清除识别结果弹窗
      setRecognitionResult(null)
    }
  }, [recognitionResult, onRecognized])

  /**
   * 处理取消识别结果
   */
  const handleCancelResult = useCallback(() => {
    setRecognitionResult(null)
  }, [])

  // ========== Render ==========

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">OCR 智能识别</CardTitle>
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={useAsync}
              onChange={(e) => setUseAsync(e.target.checked)}
              className="size-3.5 rounded"
            />
            异步模式
          </label>
        </div>
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

        {/* 拖拽上传区域 - Requirements: 6.1, 6.2 */}
        <DropZone
          isDragging={isDragging}
          isUploading={status === 'uploading'}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={handleClick}
        />

        {/* 文件预览 */}
        {selectedFile && (
          <FilePreview file={selectedFile} status={status} onRemove={handleRemoveFile} />
        )}

        {/* 异步任务进度 */}
        {taskProgress && (
          <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm text-blue-700">
            <Loader2 className="size-4 animate-spin" />
            <span>{taskProgress}</span>
          </div>
        )}

        {/* 识别结果 - Requirements: 6.7 */}
        {recognitionResult && (
          <RecognitionResult
            result={recognitionResult}
            onConfirm={handleConfirmResult}
            onCancel={handleCancelResult}
          />
        )}

        {/* 提示信息 */}
        <p className="text-muted-foreground text-xs">
          上传身份证或营业执照图片，系统将自动识别并填充相关信息。识别结果仅供参考，请核实后确认。
        </p>
      </CardContent>
    </Card>
  )
}

export default OcrUploader
