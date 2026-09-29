/** 文书识别域常量。 */

import type { ReminderTypeCode } from './types'

/** 可上传格式（与后端 recognize 端点校验一致） */
export const ACCEPT_EXTENSIONS = '.pdf,.jpg,.jpeg,.png'

/** 文件大小上限（MB）——后端未限制，前端兜底防大文件白传 */
export const MAX_FILE_MB = 20

/** 轮询节奏与上限：2s 一轮，300 轮 = 10 分钟 > 后端 q 任务 timeout 600s */
export const RECOGNIZE_POLL_MS = 2_000
export const RECOGNIZE_MAX_POLLS = 300

/**
 * 任务 404 的宽限轮数。django-q worker 摘走任务到落库有 1-3s 空窗期，
 * 期间 GET task 返回 404；连续 15 轮（30s）才认定任务真丢了。
 */
export const NOT_FOUND_GRACE_POLLS = 15

/** 提醒类型白名单（文书场景实际会用到的 ReminderType 子集） */
export const REMINDER_TYPE_OPTIONS: { value: ReminderTypeCode; label: string }[] = [
  { value: 'hearing', label: '开庭' },
  { value: 'asset_preservation_expires', label: '财产保全到期日' },
  { value: 'evidence_deadline', label: '举证到期日' },
  { value: 'appeal_deadline', label: '上诉期到期日' },
  { value: 'payment_deadline', label: '缴费期限' },
  { value: 'submission_deadline', label: '补正/材料提交期限' },
  { value: 'other', label: '其他' },
]

/** 文书类型展示 */
export const DOC_TYPE_LABELS: Record<string, string> = {
  summons: '传票',
  execution: '执行裁定书',
  other: '其他文书',
}

/** 提取方式展示（与后端 extraction_method 对齐） */
export const EXTRACTION_METHOD_LABELS: Record<string, string> = {
  vlm: 'AI 视觉',
  ocr: 'OCR',
  pdf_direct: 'PDF 直读',
  regex: '规则',
  text_extraction: '文本提取',
}

/** 候选默认勾选的置信度阈值：低于此值默认不勾，交人工判断 */
export const DEFAULT_CHECK_CONFIDENCE = 0.5

/** 分屏预览左栏宽度（%）：默认值、拖拽范围与 localStorage 记忆键 */
export const DEFAULT_SPLIT_PCT = 52
export const MIN_SPLIT_PCT = 32
export const MAX_SPLIT_PCT = 70
export const SPLIT_PCT_KEY = 'dr-split-pct'
