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
 * 执行阶段码，与后端 `PdfSplitStage`（backend/apps/pdf_splitting/models.py）逐字一致。
 * `''` 表示拿不到阶段（老任务 / 字段缺失），面板按「取字」处理。
 */
export type AutoSplitStage = 'extract' | 'cross_check' | 'segment' | 'done' | ''

/**
 * 一次轮询拿到的**结构化**进度快照。
 *
 * 以前轮询只往 UI 丢一句字符串（「正在识别 84/164 页」），阶段、耗时、心跳这些
 * 字段在 helper 内部就被丢掉了，界面上也就只能有一个工具条按钮的文字——没有进度条、
 * 没有「现在在干什么」、没有「已经花了多久」。把快照整份交出去，面板要什么自己取。
 */
export interface JobProgressSnapshot {
  jobId: string
  status: string
  /** extract / cross_check / segment / done / ''（拿不到） */
  stage: AutoSplitStage
  /** 后端原样的 progress（0-100）。注意它**不代表真实完成度**，见 `pipelineProgressPct` */
  progressPct: number
  processedPages: number
  totalPages: number
  elapsedSeconds: number | null
  staleSeconds: number | null
  errorMessage: string
  /** 交叉比对引擎（后端 `dual_engines`，逗号分隔，空串 = 不比对） */
  dualEngines: string
  /** 出问题的源文件名：接管轮询时由调用方回填，自己发起的任务为空 */
  sourceName: string
}

/**
 * 后端阶段 → 流水线真实完成度（0-100）。
 *
 * 后端在取字做完时就把 progress 写成 100、processed_pages 写满，之后还有
 * 交叉比对（164 页实测十几分钟）和 LLM 分段（4-8 分钟）——期间界面一直是 100%，
 * 就是「100% 假死」。阶段字段是唯一能把这个缺口补上的信息：
 *
 *   extract     取字：0 → 90
 *   cross_check 交叉比对：90 → 99
 *   segment     分段：99 → 100
 *   done        收尾
 *
 * 所以阶段一旦过了 extract，进度条就**不再信任**后端 progress（它只会是 100）。
 */
export function pipelineProgressPct(stage: AutoSplitStage, progressPct: number, fallbackPct = 0): number {
  if (stage === 'extract' || stage === '') {
    const pct = progressPct > 0 ? progressPct : fallbackPct
    return Math.max(0, Math.min(90, Math.round(pct * 0.9)))
  }
  if (stage === 'cross_check') return 90
  if (stage === 'segment') return 99
  return 100
}

/** 秒 → 「3 分 12 秒」这类中文友好形式。不到一分钟只报秒，律师不需要「0 分 45 秒」 */
export function formatElapsed(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return ''
  const total = Math.floor(seconds)
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  if (minutes <= 0) return `${rest} 秒`
  if (rest === 0) return `${minutes} 分钟`
  return `${minutes} 分 ${rest} 秒`
}

/** 阶段码收窄：后端将来加阶段时按「取字」保守处理，不丢整块面板 */
function toStage(raw: string | undefined): AutoSplitStage {
  return raw === 'extract' || raw === 'cross_check' || raw === 'segment' || raw === 'done' ? raw : ''
}

/**
 * 后端任务载荷 → 结构化快照。
 *
 * 参数类型刻意写成「局部放宽」而不是直接取生成物：`stage` / `started_at` /
 * `elapsed_seconds` 是后端刚加的字段，`types/api-schema.d.ts` 还是旧快照。
 * openapi 重新生成后可以去掉这里的交叉类型，直接吃 `PdfSplitJobOut`。
 */
export function jobSnapshotOf(
  job: {
    job_id: string
    status: string
    progress?: number
    total_pages?: number
    processed_pages?: number
    stale_seconds?: number | null
    error_message?: string
    dual_engines?: string
  } & { stage?: string; elapsed_seconds?: number | null; source_name?: string },
): JobProgressSnapshot {
  const totalPages = Number(job.total_pages ?? 0)
  const processedPages = Number(job.processed_pages ?? 0)
  return {
    jobId: job.job_id,
    status: job.status,
    stage: toStage(job.stage),
    progressPct: Number(job.progress ?? 0),
    processedPages,
    totalPages,
    elapsedSeconds: job.elapsed_seconds ?? null,
    staleSeconds: job.stale_seconds ?? null,
    errorMessage: job.error_message ?? '',
    dualEngines: job.dual_engines ?? '',
    sourceName: job.source_name ?? '',
  }
}

/** 轮询回调的进度文字（工具条按钮 / 旧消费方仍在用） */
function progressTextOf(snapshot: JobProgressSnapshot): string {
  // 过了取字阶段就不能再说「正在识别 X/Y 页」：页数早就满了，再报一次只会让人
  // 以为进度倒退或卡住。中文阶段名与面板同源（AutoSplitProgress 的 stageText）。
  if (snapshot.stage === 'cross_check') return '双引擎交叉比对中…'
  if (snapshot.stage === 'segment') return '正在智能分段…'
  if (snapshot.stage === 'done') return '正在收尾…'
  if (snapshot.totalPages > 0) {
    const pct = Math.min(100, Math.round((snapshot.processedPages / snapshot.totalPages) * 100))
    return `正在识别 ${snapshot.processedPages}/${snapshot.totalPages} 页（${pct}%）`
  }
  return snapshot.progressPct > 0 ? `正在识别（${snapshot.progressPct}%）` : ''
}

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

/**
 * 分段来源标记：summary 是自由字典，取不到就当规则引擎（保守，不谎报 AI 分段）。
 *
 * 后端三态：`llm` 全 LLM 批 / `mixed` 有规则降级批 / `rule` 全规则。
 * 原样透出给 `segmentBackendNote` 汇总，不在这里做语义判断。
 */
export function segmentBackendOf(job: { summary: Record<string, unknown> }): string {
  const backend = job.summary.segment_backend
  return typeof backend === 'string' ? backend : ''
}

/**
 * 段级来源是否属于「要律师重点复核的非 AI 分段」。
 *
 * 用**排除法**而不是只认 `'rule'`：规则引擎实际产出多种 source_method
 * （backend segment_detector.py：`rule` / `layout_title` / `rule_weak_only` /
 * `rule_adjacent_start` / `rule_merged_adjacent` / `gap_fill`），只认 `'rule'` 会少报，
 * 律师以为只有几段要复核。排除法对将来新增的规则变体天然生效，不会再漏。
 *
 * 排除两类：
 *  · `llm` 前缀 —— LLM 分段（后端自己也用 `startswith("llm")` 判，见 job_service.py:694）；
 *  · `manual` —— 人工确认/新建段（confirm 路径缺省即 manual，job_service.py:514）。
 *    把律师自己分的段说成「规则分段请重点复核」是倒打一耙。
 *
 * 空/缺失不判为规则（不能凭猜断言来源）。机械按页切分 `page_split` 会计入：
 * 它同样不是内容分析的结果，宁可多报也不漏报（本 feature 走 content_analysis，正常不出现）。
 */
function isReviewNeededMethod(raw: string | undefined): boolean {
  const method = (raw ?? '').trim()
  if (!method) return false
  return !method.startsWith('llm') && method !== 'manual'
}

/**
 * 一批结果里有几段是规则引擎兜的。
 *
 * 有段级 `source_method` 就**完全按它算**（哪怕算出 0）——它逐段落库，比 summary 准；
 * 一个标记都没有时才用 summary 兜底：明说全规则就按整批计，来源不明不猜成规则。
 */
export function ruleSegmentCountOf(backend: string, segments: { source_method?: string }[]): number {
  const marked = segments.filter((s) => (s.source_method ?? '').trim())
  if (marked.length > 0) return marked.filter((s) => isReviewNeededMethod(s.source_method)).length
  return backend === 'rule' ? segments.length : 0
}

/**
 * 分段来源 → 律师能据此决定要不要复核的一句话。
 *
 * `mixed`（部分批降级规则引擎）必须说出来：以前只认 llm/非 llm，mixed 会被算进
 * 「其余规则引擎」甚至「全规则」，把一次部分降级说成整份降级。规则分段的边界质量
 * 明显低于 LLM，所以带规则时把段数一并报出来，让律师知道要重点看几段。
 */
export function segmentBackendNote(backends: string[], ruleSegments: number): string {
  if (backends.length === 0) return ''
  const llm = backends.filter((b) => b === 'llm').length
  const mixed = backends.filter((b) => b === 'mixed').length
  const review = ruleSegments > 0 ? `；${ruleSegments} 段为规则分段请重点复核` : ''
  if (llm === backends.length) return '律所 AI 分段'
  if (llm === 0 && mixed === 0) return `规则引擎分段（律所 AI 不可用）${review}`
  if (llm === 0) return `律所 AI 与规则引擎混合分段${review}`
  return `${llm}/${backends.length} 律所 AI 分段，其余含规则引擎${review}`
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

/** OCR 块的最小形状：坐标可选（只给文字的老调用方仍按返回序拼） */
export interface OcrTextBlock {
  text?: string
  x?: number
  y?: number
  w?: number
  h?: number
}

type RectBlock = OcrTextBlock & { x: number; y: number; w: number; h: number }

function hasRect(b: OcrTextBlock): b is RectBlock {
  return [b.x, b.y, b.w, b.h].every((v) => typeof v === 'number' && Number.isFinite(v))
}

const centerY = (b: RectBlock): number => b.y + b.h / 2

/** y 相近算同一行：阈值取两块平均行高的 0.6（同行抖动远小于它，相邻行间距远大于它） */
function sameLine(line: RectBlock[], b: RectBlock): boolean {
  const avgY = line.reduce((sum, x) => sum + centerY(x), 0) / line.length
  const avgH = line.reduce((sum, x) => sum + x.h, 0) / line.length
  return Math.abs(centerY(b) - avgY) <= ((avgH + b.h) / 2) * 0.6
}

/**
 * OCR 文字块 → 段落文本（按坐标重建阅读顺序）。
 *
 * 引擎返回的块序不保证是阅读序（手机拍照证据尤其乱），直接 join 会把上下行、
 * 左右块交错在一起。这里按 y 聚成行、行内按 x 排：同一行的块用空格连接，
 * 行与行之间换行，保留行结构。
 *
 * 仍不出 Markdown 表格：块是「矩形 + 文字」，没有行列语义，凭空编表格会把
 * 本来就散的手机拍照证据认成一堆假表格。
 *
 * 坐标不全时不猜阅读序，保持返回序。局限：真多栏版面同一 y 上的左右栏会被排成
 * 一行（分栏需要 x 聚类，对单栏拍照证据反而会误切），这里不做。
 */
export function blocksToMarkdown(blocks: OcrTextBlock[] | undefined): string {
  const items = (blocks ?? [])
    .map((b) => ({ ...b, text: (b.text ?? '').trim() }))
    .filter((b) => b.text)
  if (!items.length) return ''
  if (!items.every(hasRect)) return items.map((b) => b.text).join('\n')
  const rects = items as RectBlock[]
  const lines: RectBlock[][] = []
  for (const b of [...rects].sort((a, z) => centerY(a) - centerY(z) || a.x - z.x)) {
    const line = lines[lines.length - 1]
    if (line && sameLine(line, b)) line.push(b)
    else lines.push([b])
  }
  return lines
    .map((line) => line.sort((a, z) => a.x - z.x).map((b) => b.text).join(' '))
    .join('\n')
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
  /** 第二个参数是结构化快照（面板用），第三个是等价的文字（工具条仍用它） */
  onProgress?: (text: string, snapshot: JobProgressSnapshot) => void,
  /** true：心跳停了只**提示**、不抛错（接管他人的任务时由用户决定是否放弃） */
  tolerateStale = false,
  staleSecondsLimit = STALE_SECONDS_LIMIT,
) {
  for (let attempt = 0; attempt < POLL_LIMIT; attempt++) {
    if (lease.isStale()) throw new Error('已取消')
    const job = await getPdfSplitJob(jobId)
    if (job.status === 'review_required' || job.status === 'completed') return job
    if (job.status === 'failed' || job.status === 'cancelled') {
      throw new Error(job.error_message || `PDF 拆分任务${job.status === 'failed' ? '失败' : '已取消'}`)
    }

    // 进度：文字喂工具条按钮，快照喂底部进度面板（页数 / 阶段 / 耗时 / 心跳）
    const snapshot = jobSnapshotOf(job)
    onProgress?.(progressTextOf(snapshot), snapshot)

    // 停滞检测：后端心跳停了就说明 worker 已死（见 backend job_recovery.py）。
    // 自己发起的任务立刻失败并给出可操作的原因——律师正等着它跑完，没有别的选择；
    // 接管来的人员作任务则只提示（tolerateStale）：它可能是别人机器上还在跑的大卷宗，
    // 替别人按下「放弃」不是我们该做的决定，交给面板上的用户自己判断。
    if (!tolerateStale && job.stale_seconds != null && job.stale_seconds > staleSecondsLimit) {
      throw new Error(
        `识别进程已中断（${Math.round(job.stale_seconds / 60)} 分钟无响应）。` +
          '请稍后重试；若反复中断，可先拆分页数再识别。',
      )
    }

    await lease.sleep(POLL_DELAY_MS)
  }
  throw new Error('云端识别等待超时，请稍后重试')
}
