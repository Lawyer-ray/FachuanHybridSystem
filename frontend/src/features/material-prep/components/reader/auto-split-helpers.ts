import { getPdfSplitJob } from '../../api'
import type { PollLease } from '@/hooks/use-poll-session'

/**
 * `useAutoSplit` 的纯逻辑/无状态助手：轮询、取材辅助、OCR 块拼文。
 *
 * 单独成文件的原因：这些函数与 hook 的 state 生命周期无关（不读 store、不碰 React），
 * 混在 hook 文件里会把那个文件顶过规模红线，也让「编排流程」与「单个请求怎么轮询」
 * 两个关注点黏在一起。轮询参数（间隔/上限/停滞阈值）跟着 `pollJob` 一起搬走。
 */

export const POLL_DELAY_MS = 2000
export const POLL_LIMIT = 420

/**
 * 后端心跳停多久算「已中断」。
 *
 * 与 `backend/apps/pdf_splitting/services/job_recovery.py` 的 `STALE_SECONDS`
 * 同口径（600s = 10 分钟），但这里放宽到 720s：前端多等两分钟没代价，
 * 误报「已中断」却会让律师主动打断一个其实还在跑的任务。
 */
export const STALE_SECONDS_LIMIT = 720

/**
 * 从材料包标题与各素材文件名里取「提示名」。
 *
 * 取的是**字**而不是分词结果：标题常写成「张三诉甲公司借款合同纠纷（扫描件）」这种
 * 连写的句子，没有词边界可切。所以按标点切成最短的短片段再互相去重 ——
 * 「张三诉甲公司」会同时给出「张三」和「甲公司」，真名字自然成为更长片段的子串，
 * 由 `detectParties` 的包含匹配挑出来；切碎了也无害（切出来的片段当不上名字就不匹配）。
 *
 * 只用「、」这类中文标点分段、再去掉扩号注释，剩下的连续中文段直接输出去重。
 */
export function hintNamesOf(subject: string | undefined, mats: { n: string; customName?: string }[]): string[] {
  const sources = [subject ?? '', ...mats.flatMap((m) => [m.customName ?? '', m.n])]
  const out: string[] = []
  for (const source of sources) {
    if (!source) continue
    // 去掉扩展名、扩号注释（「（扫描件）」这类复数不是名字），再去掉常见程序词
    const cleaned = source
      .replace(/\.[A-Za-z0-9]{1,5}$/, '')
      .replace(/[（(][^（）()]*[）)]/g, ' ')
      .replace(/(诉讼材料|证据材料|扫描件|复印件|材料包|诉讼|材料|卷宗|案卷|档案)/g, ' ')
    for (const piece of cleaned.split(/[\s、，,。；;：:【】[\]《》〈〉「」“”"'|/\\_+\-—~·]+/)) {
      const name = piece.trim()
      if (name.length >= 2 && /[\u4e00-\u9fa5]/.test(name)) out.push(name)
    }
  }
  return [...new Set(out)]
}

/** 分段来源标记：summary 是自由字典，取不到就当规则引擎（保守，不谎报 AI 分段） */
export function segmentBackendOf(job: { summary: Record<string, unknown> }): string {
  const backend = job.summary.segment_backend
  return typeof backend === 'string' ? backend : ''
}

/** 由文件名推图片 MIME（后端只存 content_type，缺失时靠它补齐） */
export function guessImageType(name: string): string {
  const lower = name.toLowerCase()
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.webp')) return 'image/webp'
  if (lower.endsWith('.gif')) return 'image/gif'
  if (lower.endsWith('.bmp')) return 'image/bmp'
  if (lower.endsWith('.tif') || lower.endsWith('.tiff')) return 'image/tiff'
  if (lower.endsWith('.heic') || lower.endsWith('.heif')) return 'image/heic'
  return 'image/jpeg'
}

/**
 * OCR 文字块 → 段落文本。
 *
 * 只拼文字、不出 Markdown 表格：框选取字的 blocks 是「矩形 + 文字」，没有
 * 行列语义，凭空编表格会把本来就散的手机拍照证据认成一堆假表格。行间用
 * 换行、块间空行，尽量保留阅读顺序（后端按识别顺序返回）。
 */
export function blocksToMarkdown(blocks: { text?: string }[] | undefined): string {
  const lines = (blocks ?? []).map((b) => (b.text ?? '').trim()).filter(Boolean)
  return lines.join('\n')
}

/**
 * 轮询云端拆分任务，并把页级进度报给 UI。
 *
 * 三件事以前都没有，导致律师只能干等：
 *  1. 显示「已识别 X/Y 页」，而不是一个万年不变的转圈；
 *  2. 停滞检测——后端心跳停了就立刻报「可能已中断」+ 重试入口，
 *     不再等到 420 次 × 2 秒 = 14 分钟才报超时（真实踩过：164 页卡在
 *     135 页二十多分钟，律师完全无从判断）；
 *  3. 把已处理页数作为「有进展」的证据，让等待有确定性。
 */
export async function pollJob(
  jobId: string,
  lease: PollLease,
  onProgress?: (text: string) => void,
  staleSecondsLimit = STALE_SECONDS_LIMIT,
) {
  for (let attempt = 0; attempt < POLL_LIMIT; attempt++) {
    if (lease.isStale()) throw new Error('已取消')
    const job = await getPdfSplitJob(jobId)
    if (job.status === 'review_required' || job.status === 'completed') return job
    if (job.status === 'failed' || job.status === 'cancelled') {
      throw new Error(job.error_message || `PDF 拆分任务${job.status === 'failed' ? '失败' : '已取消'}`)
    }

    // 页级进度：后端返回 processed_pages / total_pages，直接给律师看确定性
    if (job.total_pages > 0) {
      const pct = Math.min(100, Math.round((job.processed_pages / job.total_pages) * 100))
      onProgress?.(`正在识别 ${job.processed_pages}/${job.total_pages} 页（${pct}%）`)
    }

    // 停滞检测：后端心跳停了就说明 worker 已死（见 backend job_recovery.py），
    // 立刻失败并给出可操作的原因，而不是让律师继续盯着一个已经不会动的进度条。
    if (job.stale_seconds != null && job.stale_seconds > staleSecondsLimit) {
      throw new Error(
        `识别进程已中断（${Math.round(job.stale_seconds / 60)} 分钟无响应）。` +
          '请稍后重试；若反复中断，可先拆分页数再识别。',
      )
    }

    await lease.sleep(POLL_DELAY_MS)
  }
  throw new Error('云端识别等待超时，请稍后重试')
}
