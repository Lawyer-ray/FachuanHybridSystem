/**
 * ManualBindingDialog - 手动绑定对话框组件
 * @module features/automation/document-recognition/components/ManualBindingDialog
 *
 * 当自动绑定失败时，提供手动选择案件进行绑定的对话框
 * - 集成案件搜索选择
 * - 支持修改文书类型和关键时间
 * - 表单验证（Zod + React Hook Form）
 * - 提交状态处理
 *
 * Requirements: 7.5, 7.6, 7.7, 7.8
 */

import { useCallback, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'

import { CaseSearchSelect } from './CaseSearchSelect'
import { useBindCase } from '../hooks/use-recognition-mutations'
import { manualBindingSchema, type ManualBindingFormData } from '../schemas'
import type { DocumentRecognitionTask, CaseSearchResult } from '../types'

// ============================================================================
// Types
// ============================================================================

/**
 * ManualBindingDialog Props
 */
export interface ManualBindingDialogProps {
  /** 对话框开关 */
  open: boolean
  /** 关闭回调 */
  onOpenChange: (open: boolean) => void
  /** 识别任务 */
  task: DocumentRecognitionTask
  /** 绑定成功回调 */
  onBindSuccess?: () => void
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 手动绑定对话框组件
 *
 * 当自动绑定失败时，用户可以通过此对话框手动选择案件进行绑定。
 * 支持修改文书类型和关键时间。
 *
 * Requirements:
 * - 7.5: 当自动绑定失败时显示手动绑定界面
 * - 7.6: 提供案件搜索功能用于手动绑定
 * - 7.7: 显示匹配的案件列表
 * - 7.8: 用户选择案件并确认绑定后调用绑定 API 并更新状态
 *
 * @example
 * ```tsx
 * const [open, setOpen] = useState(false)
 *
 * <ManualBindingDialog
 *   open={open}
 *   onOpenChange={setOpen}
 *   task={recognitionTask}
 *   onBindSuccess={() => {
 *     // 刷新数据或其他操作
 *   }}
 * />
 * ```
 */
export function ManualBindingDialog({
  open,
  onOpenChange,
  task,
  onBindSuccess,
}: ManualBindingDialogProps) {
  // ========== State ==========
  // 用于存储选中的案件对象（用于显示）
  // const [selectedCase, setSelectedCase] = useState<CaseSearchResult | null>(null)

  // ========== Form Setup ==========
  const form = useForm<ManualBindingFormData>({
    resolver: zodResolver(manualBindingSchema),
    defaultValues: {
      case_id: undefined,
      document_type: task.document_type ?? '',
      key_time: task.key_time ?? '',
    },
  })

  // ========== Mutation ==========
  // Requirements: 7.8 - 调用绑定 API
  const bindCase = useBindCase()

  // ========== Effects ==========

  /**
   * 对话框打开时重置表单为任务的当前值
   */
  useEffect(() => {
    if (open) {
      form.reset({
        case_id: undefined,
        document_type: task.document_type ?? '',
        key_time: task.key_time ?? '',
      })
    }
  }, [open, task, form])

  // ========== Event Handlers ==========

  /**
   * 案件选择处理
   * Requirements: 7.6, 7.7
   */
  const handleCaseSelect = useCallback(
    (case_: CaseSearchResult) => {
      form.setValue('case_id', case_.id, { shouldValidate: true })
    },
    [form]
  )

  /**
   * 表单提交处理
   * Requirements: 7.8
   */
  const handleSubmit = useCallback(
    async (data: ManualBindingFormData) => {
      bindCase.mutate(
        {
          taskId: task.id,
          data: {
            case_id: data.case_id,
            document_type: data.document_type || undefined,
            key_time: data.key_time || undefined,
          },
        },
        {
          onSuccess: () => {
            // 关闭对话框
            onOpenChange(false)
            // 重置表单
            form.reset()
            // 调用成功回调
            onBindSuccess?.()
          },
          onError: (error) => {
            // 错误已在 useBindCase 中处理（显示 toast）
            // 这里可以添加额外的错误处理逻辑
            console.error('绑定失败:', error)
          },
        }
      )
    },
    [bindCase, task.id, onOpenChange, form, onBindSuccess]
  )

  /**
   * 取消按钮处理
   */
  const handleCancel = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  // ========== Computed ==========

  // 获取当前选中的案件 ID 用于 CaseSearchSelect 的 value 显示
  const selectedCaseId = form.watch('case_id')

  // ========== Render ==========

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>手动绑定案件</DialogTitle>
          <DialogDescription>
            自动绑定失败，请手动搜索并选择要绑定的案件。您也可以修改文书类型和关键时间。
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            {/* ========== 文件信息（只读） ========== */}
            <div className="bg-muted/50 rounded-lg p-3">
              <div className="text-muted-foreground text-xs">当前文件</div>
              <div className="text-foreground mt-1 truncate text-sm font-medium">
                {task.file_name}
              </div>
            </div>

            {/* ========== 案件选择 ========== */}
            {/* Requirements: 7.6, 7.7 */}
            <FormField
              control={form.control}
              name="case_id"
              render={() => (
                <FormItem>
                  <FormLabel>
                    选择案件 <span className="text-destructive">*</span>
                  </FormLabel>
                  <FormControl>
                    <CaseSearchSelect
                      value={
                        selectedCaseId
                          ? { id: selectedCaseId, name: '', case_number: '' }
                          : null
                      }
                      onSelect={handleCaseSelect}
                      placeholder="搜索案件名称或案号..."
                      disabled={bindCase.isPending}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* ========== 文书类型 ========== */}
            <FormField
              control={form.control}
              name="document_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>文书类型</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="如：判决书、裁定书、调解书等"
                      {...field}
                      value={field.value ?? ''}
                      disabled={bindCase.isPending}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* ========== 关键时间 ========== */}
            <FormField
              control={form.control}
              name="key_time"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>关键时间</FormLabel>
                  <FormControl>
                    <Input
                      type="date"
                      {...field}
                      value={field.value ?? ''}
                      disabled={bindCase.isPending}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* ========== 操作按钮 ========== */}
            <DialogFooter className="pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={handleCancel}
                disabled={bindCase.isPending}
              >
                取消
              </Button>
              <Button type="submit" disabled={bindCase.isPending}>
                {bindCase.isPending ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    绑定中...
                  </>
                ) : (
                  '确认绑定'
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default ManualBindingDialog
