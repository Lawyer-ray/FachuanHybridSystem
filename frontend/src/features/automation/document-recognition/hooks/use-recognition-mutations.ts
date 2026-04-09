/**
 * useRecognitionMutations Hook
 * 文书智能识别 Mutation Hooks
 *
 * 使用 TanStack Query v5 实现文书上传、案件绑定、识别信息更新操作
 * 配置缓存失效策略，确保数据一致性
 * 处理成功/失败 toast 提示
 *
 * Requirements: 6.5, 7.8, 7.9
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'
import { toast } from 'sonner'

import { documentRecognitionApi } from '../api'
import type {
  DocumentRecognitionTask,
  ManualBindingRequest,
  UpdateRecognitionInfoRequest,
} from '../types'
import { recognitionTaskQueryKey } from './use-recognition-tasks'

// ============================================================================
// Types
// ============================================================================

/**
 * useUploadDocument 返回值类型
 */
export type UseUploadDocumentResult = UseMutationResult<
  DocumentRecognitionTask,
  Error,
  File
>

/**
 * useBindCase 参数类型
 */
export interface BindCaseParams {
  /** 识别任务 ID */
  taskId: number
  /** 绑定请求数据 */
  data: ManualBindingRequest
}

/**
 * useBindCase 返回值类型
 */
export type UseBindCaseResult = UseMutationResult<
  DocumentRecognitionTask,
  Error,
  BindCaseParams
>

/**
 * useUpdateRecognitionInfo 参数类型
 */
export interface UpdateRecognitionInfoParams {
  /** 识别任务 ID */
  taskId: number
  /** 更新请求数据 */
  data: UpdateRecognitionInfoRequest
}

/**
 * useUpdateRecognitionInfo 返回值类型
 */
export type UseUpdateRecognitionInfoResult = UseMutationResult<
  DocumentRecognitionTask,
  Error,
  UpdateRecognitionInfoParams
>

// ============================================================================
// Hooks
// ============================================================================

/**
 * 上传文档进行识别 Mutation Hook
 *
 * POST /api/v1/automation/document-recognition/upload/
 *
 * 上传成功后创建识别任务，可导航到详情页查看识别进度
 *
 * @returns TanStack Query Mutation 结果
 *
 * @example
 * ```tsx
 * const uploadDocument = useUploadDocument()
 *
 * // 上传文件
 * uploadDocument.mutate(file)
 *
 * // 带回调 - 上传成功后导航到详情页
 * uploadDocument.mutate(file, {
 *   onSuccess: (task) => {
 *     navigate(`/admin/automation/document-recognition/${task.id}`)
 *   },
 * })
 *
 * // 在文件上传组件中使用
 * function FileUploader() {
 *   const uploadDocument = useUploadDocument()
 *
 *   const handleFileSelect = (file: File) => {
 *     uploadDocument.mutate(file, {
 *       onSuccess: (task) => {
 *         navigate(`/admin/automation/document-recognition/${task.id}`)
 *       },
 *     })
 *   }
 *
 *   return (
 *     <input
 *       type="file"
 *       onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
 *       disabled={uploadDocument.isPending}
 *     />
 *   )
 * }
 * ```
 *
 * Requirements: 6.5 (文件上传成功后创建识别任务并导航到详情页)
 */
export function useUploadDocument(): UseUploadDocumentResult {
  const queryClient = useQueryClient()

  return useMutation<DocumentRecognitionTask, Error, File>({
    mutationFn: (file: File) => documentRecognitionApi.upload(file),
    onSuccess: () => {
      // 上传成功后，失效所有识别任务列表缓存以刷新数据
      queryClient.invalidateQueries({
        queryKey: ['recognition-tasks'],
      })
      // 显示成功提示
      toast.success('文件上传成功，开始识别')
    },
    onError: (error) => {
      // 显示错误提示
      toast.error(`文件上传失败: ${error.message}`)
    },
  })
}

/**
 * 手动绑定案件 Mutation Hook
 *
 * POST /api/v1/automation/document-recognition/{id}/bind/
 *
 * 当自动绑定失败时，用户可以手动选择案件进行绑定
 *
 * @returns TanStack Query Mutation 结果
 *
 * @example
 * ```tsx
 * const bindCase = useBindCase()
 *
 * // 绑定案件
 * bindCase.mutate({
 *   taskId: 123,
 *   data: {
 *     case_id: 456,
 *     document_type: '判决书',
 *     key_time: '2024-01-15',
 *   },
 * })
 *
 * // 带回调
 * bindCase.mutate(
 *   { taskId: 123, data: { case_id: 456 } },
 *   {
 *     onSuccess: (task) => {
 *       console.log('绑定成功，案件:', task.case_name)
 *       onClose() // 关闭对话框
 *     },
 *   }
 * )
 *
 * // 在手动绑定对话框中使用
 * function ManualBindingDialog({ taskId, onClose }) {
 *   const bindCase = useBindCase()
 *
 *   const handleSubmit = (data: ManualBindingRequest) => {
 *     bindCase.mutate(
 *       { taskId, data },
 *       { onSuccess: () => onClose() }
 *     )
 *   }
 *
 *   return (
 *     <form onSubmit={handleSubmit}>
 *       ...
 *       <button disabled={bindCase.isPending}>
 *         {bindCase.isPending ? '绑定中...' : '确认绑定'}
 *       </button>
 *     </form>
 *   )
 * }
 * ```
 *
 * Requirements: 7.8 (用户选择案件并确认绑定后调用绑定 API 并更新状态)
 */
export function useBindCase(): UseBindCaseResult {
  const queryClient = useQueryClient()

  return useMutation<DocumentRecognitionTask, Error, BindCaseParams>({
    mutationFn: ({ taskId, data }: BindCaseParams) =>
      documentRecognitionApi.bind(taskId, data),
    onSuccess: (updatedTask, { taskId }) => {
      // 更新缓存中的识别任务详情数据
      queryClient.setQueryData(recognitionTaskQueryKey(taskId), updatedTask)
      // 失效列表缓存以刷新状态
      queryClient.invalidateQueries({
        queryKey: ['recognition-tasks'],
      })
      // 显示成功提示
      toast.success('案件绑定成功')
    },
    onError: (error) => {
      // 显示错误提示
      toast.error(`案件绑定失败: ${error.message}`)
    },
  })
}

/**
 * 更新识别信息 Mutation Hook
 *
 * PATCH /api/v1/automation/document-recognition/{id}/
 *
 * 允许用户修改识别结果（文书类型、关键时间）
 *
 * @returns TanStack Query Mutation 结果
 *
 * @example
 * ```tsx
 * const updateRecognitionInfo = useUpdateRecognitionInfo()
 *
 * // 更新文书类型
 * updateRecognitionInfo.mutate({
 *   taskId: 123,
 *   data: { document_type: '裁定书' },
 * })
 *
 * // 更新关键时间
 * updateRecognitionInfo.mutate({
 *   taskId: 123,
 *   data: { key_time: '2024-02-20' },
 * })
 *
 * // 同时更新多个字段
 * updateRecognitionInfo.mutate({
 *   taskId: 123,
 *   data: {
 *     document_type: '判决书',
 *     key_time: '2024-01-15',
 *   },
 * })
 *
 * // 在识别结果编辑组件中使用
 * function RecognitionResultEditor({ task }) {
 *   const updateInfo = useUpdateRecognitionInfo()
 *
 *   const handleSave = (data: UpdateRecognitionInfoRequest) => {
 *     updateInfo.mutate(
 *       { taskId: task.id, data },
 *       {
 *         onSuccess: () => {
 *           setEditMode(false)
 *         },
 *       }
 *     )
 *   }
 *
 *   return (
 *     <form onSubmit={handleSave}>
 *       <input name="document_type" defaultValue={task.document_type} />
 *       <input name="key_time" type="date" defaultValue={task.key_time} />
 *       <button disabled={updateInfo.isPending}>
 *         {updateInfo.isPending ? '保存中...' : '保存'}
 *       </button>
 *     </form>
 *   )
 * }
 * ```
 *
 * Requirements: 7.9 (允许用户修改识别结果：文书类型、关键时间)
 */
export function useUpdateRecognitionInfo(): UseUpdateRecognitionInfoResult {
  const queryClient = useQueryClient()

  return useMutation<DocumentRecognitionTask, Error, UpdateRecognitionInfoParams>({
    mutationFn: ({ taskId, data }: UpdateRecognitionInfoParams) =>
      documentRecognitionApi.updateInfo(taskId, data),
    onSuccess: (updatedTask, { taskId }) => {
      // 更新缓存中的识别任务详情数据
      queryClient.setQueryData(recognitionTaskQueryKey(taskId), updatedTask)
      // 失效列表缓存以刷新状态
      queryClient.invalidateQueries({
        queryKey: ['recognition-tasks'],
      })
      // 显示成功提示
      toast.success('识别信息更新成功')
    },
    onError: (error) => {
      // 显示错误提示
      toast.error(`更新识别信息失败: ${error.message}`)
    },
  })
}

export default {
  useUploadDocument,
  useBindCase,
  useUpdateRecognitionInfo,
}
