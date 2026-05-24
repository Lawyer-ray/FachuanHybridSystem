import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contentOpsApi } from '../api'
import type { CreateTaskInput, ReviewActionInput, TopicSuggestion } from '../types'

// 任务关联讨论稿
export function useTaskDiscussions(taskId: number | null) {
  return useQuery({
    queryKey: ['content-ops', 'task', taskId, 'discussions'],
    queryFn: () => contentOpsApi.getTaskDiscussions(taskId!),
    enabled: !!taskId,
  })
}

// 讨论稿详情
export function useDiscussionDetail(scriptId: number | null) {
  return useQuery({
    queryKey: ['content-ops', 'discussion', scriptId],
    queryFn: () => contentOpsApi.getDiscussion(scriptId!),
    enabled: !!scriptId,
  })
}

// 选题建议（手动触发，使用 mutation，带错误处理）
export function useTopicSuggestions() {
  const [data, setData] = useState<TopicSuggestion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: (model?: string) => contentOpsApi.suggestTopics(model),
    onSuccess: (result) => {
      setData(result)
      setError(null)
    },
    onError: (err: Error) => {
      setError(err.message || '获取选题建议失败')
    },
  })

  return {
    data,
    error,
    isFetching: mutation.isPending,
    refetch: (model?: string) => mutation.mutateAsync(model),
  }
}

// 任务列表
export function useTaskList(mode?: string) {
  return useQuery({
    queryKey: ['content-ops', 'tasks', mode],
    queryFn: () => contentOpsApi.listTasks(mode),
    refetchInterval: (query) => {
      // 有运行中的任务时自动刷新
      const tasks = query.state.data
      if (tasks?.some((t) => ['pending', 'queued', 'running'].includes(t.status))) {
        return 3000
      }
      return false
    },
  })
}

// 任务详情
export function useTaskDetail(taskId: number | null) {
  return useQuery({
    queryKey: ['content-ops', 'task', taskId],
    queryFn: () => contentOpsApi.getTask(taskId!),
    enabled: !!taskId,
    refetchInterval: (query) => {
      const task = query.state.data
      if (task && ['pending', 'queued', 'running'].includes(task.status)) {
        return 2000
      }
      return false
    },
  })
}

// 任务关联文章
export function useTaskArticles(taskId: number | null) {
  return useQuery({
    queryKey: ['content-ops', 'task', taskId, 'articles'],
    queryFn: () => contentOpsApi.getTaskArticles(taskId!),
    enabled: !!taskId,
  })
}

// 任务关联音频
export function useTaskEpisodes(taskId: number | null) {
  return useQuery({
    queryKey: ['content-ops', 'task', taskId, 'episodes'],
    queryFn: () => contentOpsApi.getTaskEpisodes(taskId!),
    enabled: !!taskId,
  })
}

// 创建任务
export function useCreateTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTaskInput) => contentOpsApi.createTask(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops', 'tasks'] })
    },
  })
}

// 审核文章
export function useReviewArticle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ articleId, action, notes }: { articleId: number; action: 'approve' | 'reject'; notes?: string }) => {
      const data: ReviewActionInput = { notes }
      return action === 'approve'
        ? contentOpsApi.approveArticle(articleId, data)
        : contentOpsApi.rejectArticle(articleId, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 编辑文章
export function useUpdateArticle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ articleId, title, content }: { articleId: number; title?: string; content?: string }) =>
      contentOpsApi.updateArticle(articleId, { title, content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 重新生成文章
export function useRegenerateArticle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (articleId: number) => contentOpsApi.regenerateArticle(articleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 审核音频
export function useReviewEpisode() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ episodeId, action, notes }: { episodeId: number; action: 'approve' | 'reject'; notes?: string }) => {
      const data: ReviewActionInput = { notes }
      return action === 'approve'
        ? contentOpsApi.approveEpisode(episodeId, data)
        : contentOpsApi.rejectEpisode(episodeId, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 重试任务
export function useRetryTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (taskId: number) => contentOpsApi.retryTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 取消任务
export function useCancelTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (taskId: number) => contentOpsApi.cancelTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 删除任务
export function useDeleteTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (taskId: number) => contentOpsApi.deleteTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 编辑讨论稿轮次
export function useUpdateDiscussionTurn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ turnId, text, speaker_style_prompt }: { turnId: number; text?: string; speaker_style_prompt?: string }) =>
      contentOpsApi.updateDiscussionTurn(turnId, { text, speaker_style_prompt }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 审核讨论稿
export function useReviewDiscussion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ scriptId, action, notes }: { scriptId: number; action: 'approve' | 'reject'; notes?: string }) => {
      const data: ReviewActionInput = { notes }
      return action === 'approve'
        ? contentOpsApi.approveDiscussion(scriptId, data)
        : contentOpsApi.rejectDiscussion(scriptId, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 重新生成讨论稿
export function useRegenerateDiscussion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (scriptId: number) => contentOpsApi.regenerateDiscussion(scriptId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}

// 合成讨论稿音频
export function useSynthesizeDiscussion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (scriptId: number) => contentOpsApi.synthesizeDiscussion(scriptId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['content-ops'] })
    },
  })
}
