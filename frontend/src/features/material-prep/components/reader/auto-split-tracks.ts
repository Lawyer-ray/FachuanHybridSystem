import { createPdfSplitJob, fetchAttachmentBytes, findReusablePdfSplitJob, ocrImage, parseOfficeFile } from '../../api'
import {
  readEngineDisagreements,
  readInconsistencies,
  readJudgeState,
  readPageAnomaly,
  readPageQuality,
} from '../../draft'
import type {
  BundleMat,
  EngineDisagreement,
  Inconsistency,
  JudgeState,
  PageAnomaly,
  PageQuality,
  PdfSplitSegmentSuggestion,
} from '../../types'
import type { CloudBackend } from '../../api'
import type { PollLease } from '@/hooks/use-poll-session'
import { blocksToMarkdown, guessImageType, pollJob, segmentBackendOf, type JobProgressSnapshot } from './auto-split-helpers'
import type { MatTarget } from './auto-split-targets'

/**
 * 三种材料各走哪条轨道、拿到什么结果。
 *
 * 三条轨分开写而不是在一个循环里 switch：
 *  · PDF 轨要提交云端任务 + 串行轮询（分钟级、要花钱）；
 *  · 图片轨是单页取字（秒级）；
 *  · Office 轨是本地 OOXML 解析（不联网）。
 * 各自的失败**互不拖累**（图片识别失败不该把已经跑完的 PDF 分段一起丢掉），
 * 失败数也分开数——混在一起报「完成 N 份」会让律师以为图片也分了段。
 */

/**
 * 单个 PDF 的云端拆分结果：mi 定位材料，segmentBackend 用于提示分段质量来源。
 * 另带五类「机器读到什么」的统计（都可能缺，旧任务 / 后端未算时为空）：
 *   · page_quality —— 哪几页是图纸/照片、哪几页几乎没字（→ 段行标记 + 正文提示条）
 *   · pageAnomaly —— 哪几页云端取字判为退化、哪几页表格列数与邻页不同
 *     （→ 页级风险提示，派生见 `draft/page-anomaly.ts`）
 *   · inconsistencies —— 同一枚章 / 同一个字段被识别成两种写法（→ 全局清单）
 *   · engineDisagreements —— 两个 OCR 引擎在同一处读得不一样（→ 引擎分歧清单 + 双框）
 *   · judgeState —— 这些分歧到底有没有被自动裁定，没裁是因为什么（→ 顶部提示条 + 收尾提示）
 *
 * 没跑交叉比对时（存量包默认 / 律师一键关闭）`engine_disagreements` 整个键都不存在，
 * 收窄后为空数组。新建包默认开双引擎，见 constants.defaultRecognition。
 *
 * `judgeState` 与前三类的区别：它不描述「读到了什么」，而描述「那一步**跑没跑**」。
 * 这正是以前缺的那一环——后端从 v27.25.4 就在 summary 里给了这个键，前端一个都没读。
 */
export interface AutoSplitResult {
  mi: number
  /** 产出这批段的任务号（→ `Segment.splitRef`，下载已切好的 pdf/md 靠它定位） */
  jobId: string
  segments: PdfSplitSegmentSuggestion[]
  segmentBackend: string
  pageQuality: PageQuality | null
  pageAnomaly: PageAnomaly | null
  inconsistencies: Inconsistency[]
  engineDisagreements: EngineDisagreement[]
  /** 分歧裁定的门禁结果；旧任务为 null（那时没有这个键） */
  judgeState: JudgeState | null
}

/** 一条旁路轨道的产物：哪份素材 + 取到的正文（空正文不入列） */
export interface ExtractedText {
  mi: number
  md: string
}

export interface TrackOutcome {
  /** 会话已过期（连点重入 / 关掉阅读器）：调用方必须立刻停手，不再回写 */
  stale: boolean
  texts: ExtractedText[]
  failed: number
}

export interface PdfTrackOutcome {
  stale: boolean
  results: AutoSplitResult[]
  /** 失败的 PDF（`PromiseSettledResult` 原样带出：全部失败时要拿第一条的 reason 报错） */
  failures: PromiseSettledResult<AutoSplitResult>[]
}

/**
 * PDF 轨：提交云端拆分任务（或复用已有任务）→ 串行轮询到终态。
 *
 * **先查有没有已经算好的任务可直接复用。** 真实痛点：164 页材料跑一次要 5-10 分钟
 * + 几十元（云端 OCR + LLM 分段），但只要 draft_state 没回写（没点过按钮 / 换浏览器），
 * 阅读器就拿不到结果，一点「自动识别」就从零重跑。匹配口径（文件名 + 页数 + 已出结果）
 * 在后端 find_reusable_job 里。
 *
 * 轮询**串行**：过期会话（连点重入 / 卸载）在下一个自检点退出，不再产生新请求。
 */
export async function runPdfTrack(args: {
  openId: number
  targets: MatTarget[]
  /** 轮询会话 lease：串行轮询每个 await 前后自检，并据此可中断 sleep */
  lease: PollLease
  /** 工具条那一行文字（它只有一行的宽度） */
  setProgress: (text: string) => void
  /** 底部面板要的整份快照（阶段 / 页数 / 耗时 / 心跳） */
  reportProgress: (snapshot: JobProgressSnapshot) => void
  layoutMode: 'fast_text' | 'layout'
  cloudBackend: CloudBackend
  dualEngines: string | null
  segmentStrategy: string
  ocrJudgeEnabled: boolean
}): Promise<PdfTrackOutcome> {
  const {
    openId,
    targets,
    lease,
    setProgress,
    reportProgress,
    layoutMode,
    cloudBackend,
    dualEngines,
    segmentStrategy,
    ocrJudgeEnabled,
  } = args
  const isStale = () => lease.isStale()
  const jobs = await Promise.all(
    targets.map(async ({ mat, mi }) => {
      // 带上材料包主键：同名同页数的两份文件分属两个包时，只按这两维匹配会把
      // **另一个包**的识别结果拿进来——那份正文会被写进这个包的草稿里。
      const reusable = await findReusablePdfSplitJob({
        packMessageId: openId,
        sourceName: mat.n,
        totalPages: mat.pages,
      })
      if (reusable?.segments?.length) {
        setProgress(`${mat.n}：复用已有识别结果`)
        return { mi, jobId: reusable.job_id, prefetched: reusable }
      }

      const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
      const filename = mat.customName || mat.n
      const file = new File([bytes], filename.toLowerCase().endsWith('.pdf') ? filename : `${filename}.pdf`, {
        type: 'application/pdf',
      })
      // 版面策略跟着当前会话走：开了补版面才让电子页上云端拿坐标
      return {
        mi,
        jobId: await createPdfSplitJob(file, {
          packMessageId: openId,
          layoutMode,
          cloudBackend,
          dualEngines,
          segmentStrategy,
          ocrJudgeEnabled,
        }),
        prefetched: null,
      }
    }),
  )

  // 进度有两条消费方，形态不同：工具条按钮只要一句文字，底部面板要整份快照。
  // 所以回调里同时喂两处。
  const onProgress = (text: string, snapshot: JobProgressSnapshot) => {
    setProgress(text)
    reportProgress(snapshot)
  }

  const settled: PromiseSettledResult<AutoSplitResult>[] = []
  let finished = 0
  for (const { mi, jobId, prefetched } of jobs) {
    if (isStale()) break
    try {
      // 复用的任务已经是 review_required/completed，不必再轮询一轮
      const result = prefetched ?? (await pollJob(jobId, lease, onProgress))
      if (isStale()) break
      finished += 1
      setProgress(`云端识别完成 ${finished}/${jobs.length}`)
      settled.push({
        status: 'fulfilled',
        value: {
          mi,
          jobId,
          segments: result.segments,
          segmentBackend: segmentBackendOf(result),
          pageQuality: readPageQuality(result.summary.page_quality),
          inconsistencies: readInconsistencies(result.summary.inconsistencies),
          engineDisagreements: readEngineDisagreements(result.summary.engine_disagreements),
          judgeState: readJudgeState(result.summary.engine_disagreements_judge),
          pageAnomaly: readPageAnomaly(result.summary),
        },
      })
    } catch (error) {
      settled.push({ status: 'rejected', reason: error })
    }
  }

  return {
    stale: isStale(),
    results: settled.flatMap((item) => (item.status === 'fulfilled' ? [item.value] : [])),
    failures: settled.filter((item) => item.status === 'rejected'),
  }
}

/** 旁路轨道的取字那一步：拿到已下载的字节和它属于哪份材料，返回正文（空串 = 没取到字） */
type TextExtractor = (args: { bytes: ArrayBuffer; mat: BundleMat }) => Promise<string>

/**
 * 图片 / Office 两轨共用的骨架：逐份下载字节 → 交取字器 → 有字就收。
 *
 * 两轨**只差取字那一步**，其余完全一致：过期即停（不再发新请求）、单份失败只加计数
 * 不中断循环（一份坏图 / 加密 docx 不该让同批其它份白跑）。抽成一份是为了让这条
 * 容错口径只有一处实现，改一处两轨同时生效。
 */
async function runTextTrack(args: {
  openId: number
  targets: MatTarget[]
  isStale: () => boolean
  extract: TextExtractor
}): Promise<TrackOutcome> {
  const { openId, targets, isStale, extract } = args
  const texts: ExtractedText[] = []
  let failed = 0
  for (const { mat, mi } of targets) {
    if (isStale()) return { stale: true, texts: [], failed: 0 }
    try {
      const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
      const md = await extract({ bytes, mat })
      if (md) texts.push({ mi, md })
    } catch {
      failed += 1
    }
  }
  return { stale: false, texts, failed }
}

/**
 * 图片轨：单页取字（RapidOCR）。
 *
 * 图片不参与「分段」（本就只有一页），它要的是把这一页的文字填进段里。
 * 单独一轨是为了**避免图片识别失败拖垮 PDF 分段这条主线**。
 */
export async function runPhotoTrack(args: {
  openId: number
  targets: MatTarget[]
  isStale: () => boolean
}): Promise<TrackOutcome> {
  return runTextTrack({
    ...args,
    extract: async ({ bytes, mat }) => {
      const ocr = await ocrImage(new Blob([bytes], { type: guessImageType(mat.n) }))
      return blocksToMarkdown(ocr.blocks)
    },
  })
}

/**
 * Word / Excel 轨：单份解析取字（同样单独一轨，不与 PDF 分段互相拖累）。
 *
 * 取 `markdown || text`：能出 markdown 就出（表格/标题结构保留），不能就退回纯文本。
 */
export async function runOfficeTrack(args: {
  openId: number
  targets: MatTarget[]
  isStale: () => boolean
}): Promise<TrackOutcome> {
  return runTextTrack({
    ...args,
    extract: async ({ bytes, mat }) => {
      const parsed = await parseOfficeFile(new File([bytes], mat.customName || mat.n))
      return parsed.markdown || parsed.text
    },
  })
}
