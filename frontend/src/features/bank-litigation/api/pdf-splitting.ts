import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

import { LONG_TASK_TIMEOUT_MS } from './timeouts'

// ───────────────────────── 整包 PDF 自动分段 ─────────────────────────

/**
 * 场景 2 的**真正起点**：律师拿到的是整包扫描件，不是分好的散件。
 *
 * 链路：
 *   上传整包 → POST /pdf-splitting/jobs → 轮询 → 人工复核 → confirm
 *   → 导出 10 个独立 PDF → 逐个上传到案件 → bind 归案 → 材料齐备度自动算出
 *
 * 关键认知：**上传 ≠ 归案**。
 *   /cases/{id}/materials/upload 只是把文件塞进案件日志（CaseLogAttachment），
 *   必须再调 /materials/bind 才会变成「材料」（CaseMaterial），
 *   材料齐备度读到的是后者。少了 bind 这一步，文件传成功了但齐备度永远是 0。
 */
export const pdfSplitApi = createApiClient({ prefix: '/api/v1/pdf-splitting' })

/**
 * 分段任务的回执信封（新建 / 取消 / 确认三个动作同一个形状）。
 *
 * 单独具名是因为它被抄了 6 遍：后端给任务加字段（比如 `progress`）时，
 * 手抄版本会漏掉一半，前端就只在一部分路径上看得到新字段。
 */
export type SplitJobEnvelope = { job_id: string; status: string }

export type PdfSplitJob = components['schemas']['PdfSplitJobOut']
/**
 * 单个分段。
 *
 * ⚠️ 生成物里的名字是 `SegmentOut`（不是直觉上的 PdfSplitSegmentOut）——
 * 后端 schema 类就叫 SegmentOut。字段：page_start/page_end/segment_type/
 * segment_label/filename/confidence/review_flag/source_method。
 */
export type PdfSplitSegment = components['schemas']['SegmentOut']

/**
 * 提交自动分段任务。
 *
 * `split_mode=content_analysis` 是内容识别拆分（按每页正文判断材料类型）；
 * 另有 page_split（按页拆）与 manual_split（手工）。
 * 模板 `filing_materials_v1` 对应立案材料的一套类型（起诉状/证据清单/借款合同…），
 * 换模板会换整套识别规则，所以这里不暴露成可选项——本场景只处理立案材料。
 */
/**
 * 分段模板。**选错模板 = 认不出材料**：
 *   filing_materials_v1  一审起诉材料（起诉状/证据清单/借款合同/流水…）
 *   appeal_defense_v1    二审答辩材料（一审判决书/上诉状/答辩状/庭审笔录…）
 *
 * ⚠️ 这不是「可选项」，是「必须对上阶段」：把二审包交给一审模板，
 * 模型会按立案材料的身份预设否定判决书/上诉状，全部回 other（实测 5 段只认 1 段）。
 */
export type SplitTemplate = 'filing_materials_v1' | 'appeal_defense_v1'

export async function createSplitJob(
  file: File,
  templateKey: SplitTemplate = 'filing_materials_v1',
): Promise<SplitJobEnvelope> {
  const form = new FormData()
  form.append('file', file)
  form.append('split_mode', 'content_analysis')
  form.append('template_key', templateKey)
  form.append('ocr_profile', 'balanced')
  return pdfSplitApi
    .post('jobs', { body: form, timeout: LONG_TASK_TIMEOUT_MS })
    .json<SplitJobEnvelope>()
}

/** 查询分段任务（轮询用） */
export async function getSplitJob(jobId: string): Promise<PdfSplitJob> {
  return pdfSplitApi.get(`jobs/${jobId}`).json<PdfSplitJob>()
}

/** 取消分段任务 */
export async function cancelSplitJob(jobId: string): Promise<SplitJobEnvelope> {
  return pdfSplitApi.post(`jobs/${jobId}/cancel`).json<SplitJobEnvelope>()
}

/** 分段确认提交项（与后端 ConfirmSegmentIn 对齐） */
export interface ConfirmSegment {
  id?: number | null
  order?: number | null
  page_start: number
  page_end: number
  segment_type: string
  filename: string
  confidence?: number | null
  review_flag?: string | null
  source_method?: string | null
}

/** 确认分段（人工复核后）→ 后端开始逐个导出 PDF */
export async function confirmSplitJob(
  jobId: string,
  segments: ConfirmSegment[],
): Promise<SplitJobEnvelope> {
  return pdfSplitApi
    .post(`jobs/${jobId}/confirm`, { json: { segments }, timeout: LONG_TASK_TIMEOUT_MS })
    .json<SplitJobEnvelope>()
}

/** 下载全部拆分结果（zip） */
export async function downloadSplitZip(jobId: string): Promise<Blob> {
  const res = await pdfSplitApi.get(`jobs/${jobId}/download`, { timeout: LONG_TASK_TIMEOUT_MS })
  return res.blob()
}
