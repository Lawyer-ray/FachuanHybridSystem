import { createPdfSplitJob, fetchAttachmentBytes, findReusablePdfSplitJob, ocrImage, parseOfficeFile } from '../../api'
import { readEngineDisagreements, readInconsistencies, readPageQuality } from '../../draft'
import type { EngineDisagreement, Inconsistency, PageQuality, PdfSplitSegmentSuggestion } from '../../types'
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
 * 另带三类「机器读到什么」的统计（都可能缺，旧任务 / 后端未算时为空）：
 *   · page_quality —— 哪几页是图纸/照片、哪几页几乎没字（→ 段行标记 + 正文提示条）
 *   · inconsistencies —— 同一枚章 / 同一个字段被识别成两种写法（→ 全局清单）
 *   · engineDisagreements —— 两个 OCR 引擎在同一处读得不一样（→ 引擎分歧清单 + 双框）
 *
 * 没跑交叉比对时（存量包默认 / 律师一键关闭）`engine_disagreements` 整个键都不存在，
 * 收窄后为空数组。新建包默认开双引擎，见 constants.defaultRecognition。
 */
export interface AutoSplitResult {
  mi: number
  /** 产出这批段的任务号（→ `Segment.splitRef`，下载已切好的 pdf/md 靠它定位） */
  jobId: string
  segments: PdfSplitSegmentSuggestion[]
  segmentBackend: string
  pageQuality: PageQuality | null
  inconsistencies: Inconsistency[]
  engineDisagreements: EngineDisagreement[]
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
}): Promise<PdfTrackOutcome> {
  const { openId, targets, lease, setProgress, reportProgress, layoutMode, cloudBackend, dualEngines } = args
  const isStale = () => lease.isStale()
  const jobs = await Promise.all(
    targets.map(async ({ mat, mi }) => {
      const reusable = await findReusablePdfSplitJob(mat.n, mat.pages)
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
        jobId: await createPdfSplitJob(file, { layoutMode, cloudBackend, dualEngines }),
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
  const { openId, targets, isStale } = args
  const texts: ExtractedText[] = []
  let failed = 0
  for (const { mat, mi } of targets) {
    if (isStale()) return { stale: true, texts: [], failed: 0 }
    try {
      const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
      const blob = new Blob([bytes], { type: guessImageType(mat.n) })
      const ocr = await ocrImage(blob)
      const md = blocksToMarkdown(ocr.blocks)
      if (md) texts.push({ mi, md })
    } catch {
      failed += 1
    }
  }
  return { stale: false, texts, failed }
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
  const { openId, targets, isStale } = args
  const texts: ExtractedText[] = []
  let failed = 0
  for (const { mat, mi } of targets) {
    if (isStale()) return { stale: true, texts: [], failed: 0 }
    try {
      const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
      const file = new File([bytes], mat.customName || mat.n)
      const parsed = await parseOfficeFile(file)
      const md = parsed.markdown || parsed.text
      if (md) texts.push({ mi, md })
    } catch {
      failed += 1
    }
  }
  return { stale: false, texts, failed }
}
