import { createFeatureApiClient, resolveMediaUrl } from '@/lib/api'
import type {
  ContentTask,
  CreateTaskInput,
  DiscussionScript,
  DiscussionTurn,
  GeneratedArticle,
  PodcastEpisode,
  ReviewActionInput,
  TopicSuggestion,
} from './types'

const api = createFeatureApiClient('content-ops')

export const contentOpsApi = {
  // 选题建议（LLM 调用耗时较长，需要更长超时）
  suggestTopics: (model?: string) =>
    api.post('topics/suggest', {
      json: { model: model || '' },
      timeout: 120_000,
    }).json<TopicSuggestion[]>(),

  // 任务 CRUD
  createTask: (data: CreateTaskInput) =>
    api.post('tasks', { json: data }).json<ContentTask>(),

  listTasks: (mode?: string) =>
    api.get('tasks', { searchParams: mode ? { mode } : undefined }).json<ContentTask[]>(),

  getTask: (taskId: number) =>
    api.get(`tasks/${taskId}`).json<ContentTask>(),

  retryTask: (taskId: number) =>
    api.post(`tasks/${taskId}/retry`).json<ContentTask>(),

  cancelTask: (taskId: number) =>
    api.post(`tasks/${taskId}/cancel`).json<ContentTask>(),

  deleteTask: (taskId: number) =>
    api.delete(`tasks/${taskId}`).json<{ message: string }>(),

  // 任务关联数据
  getTaskArticles: (taskId: number) =>
    api.get(`tasks/${taskId}/articles`).json<GeneratedArticle[]>(),

  getTaskEpisodes: (taskId: number) =>
    api.get(`tasks/${taskId}/episodes`).json<PodcastEpisode[]>(),

  // 讨论稿
  getTaskDiscussions: (taskId: number) =>
    api.get(`tasks/${taskId}/discussions`).json<DiscussionScript[]>(),

  getDiscussion: (scriptId: number) =>
    api.get(`discussions/${scriptId}`).json<DiscussionScript>(),

  updateDiscussionTurn: (turnId: number, data: { text?: string; speaker_style_prompt?: string }) =>
    api.put(`discussions/turns/${turnId}`, { json: data }).json<DiscussionTurn>(),

  approveDiscussion: (scriptId: number, data?: ReviewActionInput) =>
    api.post(`discussions/${scriptId}/approve`, { json: data ?? {} }).json<DiscussionScript>(),

  rejectDiscussion: (scriptId: number, data?: ReviewActionInput) =>
    api.post(`discussions/${scriptId}/reject`, { json: data ?? {} }).json<DiscussionScript>(),

  regenerateDiscussion: (scriptId: number) =>
    api.post(`discussions/${scriptId}/regenerate`).json<DiscussionScript>(),

  synthesizeDiscussion: (scriptId: number) =>
    api.post(`discussions/${scriptId}/synthesize`).json<PodcastEpisode>(),

  // 审核操作
  approveArticle: (articleId: number, data?: ReviewActionInput) =>
    api.post(`articles/${articleId}/approve`, { json: data ?? {} }).json<GeneratedArticle>(),

  rejectArticle: (articleId: number, data?: ReviewActionInput) =>
    api.post(`articles/${articleId}/reject`, { json: data ?? {} }).json<GeneratedArticle>(),

  updateArticle: (articleId: number, data: { title?: string; content?: string }) =>
    api.put(`articles/${articleId}`, { json: data }).json<GeneratedArticle>(),

  regenerateArticle: (articleId: number) =>
    api.post(`articles/${articleId}/regenerate`).json<GeneratedArticle>(),

  batchApproveArticles: (ids: number[], notes?: string) =>
    api.post('articles/batch/approve', { json: { ids, notes: notes || '' } }).json<{ results: { id: number; success: boolean; error?: string }[] }>(),

  batchApproveEpisodes: (ids: number[], notes?: string) =>
    api.post('episodes/batch/approve', { json: { ids, notes: notes || '' } }).json<{ results: { id: number; success: boolean; error?: string }[] }>(),

  approveEpisode: (episodeId: number, data?: ReviewActionInput) =>
    api.post(`episodes/${episodeId}/approve`, { json: data ?? {} }).json<PodcastEpisode>(),

  rejectEpisode: (episodeId: number, data?: ReviewActionInput) =>
    api.post(`episodes/${episodeId}/reject`, { json: data ?? {} }).json<PodcastEpisode>(),

  // 音频 URL
  getAudioUrl: (episodeId: number) =>
    resolveMediaUrl(`/api/v1/content-ops/episodes/${episodeId}/audio`),

  // TTS 测试
  testTts: (text: string, voice: string, stylePrompt?: string) =>
    api.post('tts/test', {
      json: { text, voice, audio_format: 'mp3', style_prompt: stylePrompt ?? '' },
    }).blob(),
}
