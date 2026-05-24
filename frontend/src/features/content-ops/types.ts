/* eslint-disable react-refresh/only-export-components */

export type TaskMode = 'search' | 'direct'
export type TaskStatus = 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type ReviewStatus = 'draft' | 'approved' | 'rejected'
export type OutputMode = 'narration' | 'discussion' | 'both'
export type ContentSource = 'article' | 'discussion'

export interface TopicSuggestion {
  title: string
  description: string
  suggested_keyword: string
}

export interface DiscussionSpeaker {
  name: string
  role: string
  style_prompt: string
}

export interface DiscussionTurn {
  id: number
  speaker_name: string
  speaker_style_prompt: string
  text: string
  order: number
}

export interface DiscussionScript {
  id: number
  title: string
  topic: string
  review_status: ReviewStatus
  reviewer_notes: string
  turns: DiscussionTurn[]
  llm_model: string
  token_usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  } | null
  created_at: string
  updated_at: string
}

export interface ContentTask {
  id: number
  mode: TaskMode
  keyword: string
  case_summary: string
  voice: string
  tts_style_prompt: string
  output_mode: OutputMode
  discussion_speakers: DiscussionSpeaker[]
  source_title: string
  source_court_text: string
  source_judgment_date: string
  status: TaskStatus
  progress: number
  message: string
  error: string
  created_at: string
  updated_at: string
}

export interface GeneratedArticle {
  id: number
  title: string
  content: string
  source_summary: string
  review_status: ReviewStatus
  reviewer_notes: string
  llm_model: string
  token_usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  } | null
  created_at: string
  updated_at: string
}

export interface PodcastEpisode {
  id: number
  article_id: number | null
  discussion_script_id: number | null
  content_source: ContentSource
  voice: string
  audio_url: string
  duration_seconds: number | null
  file_size_bytes: number | null
  review_status: ReviewStatus
  reviewer_notes: string
  created_at: string
  updated_at: string
}

export interface CreateTaskInput {
  mode: TaskMode
  credential_id?: number | null
  keyword?: string
  case_summary?: string
  direct_content?: string
  voice?: string
  tts_style_prompt?: string
  output_mode?: OutputMode
  discussion_speakers?: DiscussionSpeaker[]
}

export interface ReviewActionInput {
  notes?: string
}

export const VOICE_OPTIONS = [
  { value: '冰糖', label: '冰糖' },
  { value: '茉莉', label: '茉莉' },
  { value: '苏打', label: '苏打' },
  { value: '白桦', label: '白桦' },
] as const

export const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '待处理',
  queued: '队列中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  draft: '待审核',
  approved: '已通过',
  rejected: '已驳回',
}

export const MODE_LABEL: Record<TaskMode, string> = {
  search: '检索模式',
  direct: '直投模式',
}

export const OUTPUT_MODE_LABEL: Record<OutputMode, string> = {
  narration: '单人叙事',
  discussion: '多人讨论',
  both: '两者都要',
}

export const CONTENT_SOURCE_LABEL: Record<ContentSource, string> = {
  article: '文章',
  discussion: '讨论稿',
}
