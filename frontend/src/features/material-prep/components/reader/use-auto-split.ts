import { useState } from 'react'
import { toast } from 'sonner'
import { fetchAttachmentBytes, createPdfSplitJob, findReusablePdfSplitJob, ocrImage, parseOfficeFile } from '../../api'
import {
  applyAutoSplit,
  applyAutoSplitPreservingEdits,
  canAutoSplitMat,
  detectAutoSplitConflicts,
  fillSegmentText,
  type AutoSplitConflict,
} from '../../draft'
import { useReader } from '../../store'
import { applyDetectedParties, detectParties } from '../../draft/detect-parties'
import type { DraftState, PdfSplitSegmentSuggestion } from '../../types'
import { usePollSession } from '@/hooks/use-poll-session'
import { blocksToMarkdown, guessImageType, pollJob, segmentBackendOf } from './auto-split-helpers'

/**
 * 重跑前冲突询问的三种结果。
 *
 * - `keep`：保留律师改过的东西（人工正文搬回新分段）→ `applyAutoSplitPreservingEdits`
 * - `overwrite`：以 AI 结果为准，改动会被覆盖 → `applyAutoSplit`
 * - `cancel`：整次重跑不执行
 */
export type RerunChoice = 'keep' | 'overwrite' | 'cancel'

/** 单个 PDF 的云端拆分结果：mi 定位材料，segmentBackend 用于提示分段质量来源 */
interface AutoSplitResult {
  mi: number
  segments: PdfSplitSegmentSuggestion[]
  segmentBackend: string
}

/**
 * 自动分段编排：提交云端拆分任务 → 轮询到终态 → 回写草稿。
 *
 * 重入与卸载走 usePollSession 的会话号守卫：run() 一开始就签发新会话，
 * 旧循环在下一个自检点退出。以前的 cancelled ref 只在卸载置位——连点两次
 * 会跑起两个循环，两个云端任务、两条 setProgress 流互相覆盖，回写顺序不定。
 * 工具条按钮的 disabled 只挡得住「已渲染成 running」之后的点击，
 * 挡不住同一帧/双击的这种重入。
 */
export function useAutoSplit() {
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState('')
  // 重跑前的冲突询问：非 null 时 ReaderDialogs 弹 RerunConfirmDialog，等用户选。
  // resolve 一直挂在 state 里直到用户点按钮；取消时 resolve('cancel')，整次 run 直接退出。
  const [pendingConflicts, setPendingConflicts] = useState<{
    conflicts: AutoSplitConflict[]
    draft: DraftState
    resolve: (choice: RerunChoice) => void
  } | null>(null)
  const pollSession = usePollSession()

  /**
   * 拿这次重跑的用户选择。
   *
   * 冲突**在提交云端任务之前**算：算得到的 `edited` 只依赖当前草稿，跟这次任务会返回
   * 什么建议无关（`detectAutoSplitConflicts` 只用 suggestions 判空）。放在提交前问，
   * 律师取消时一个钱不花、一个任务不建。
   *
   * 这里用一条临时占位建议骗过那层判空：我们不需要真建议，只需要「有冲突吗」这个答案。
   * 真建议此刻还没拿到——它正是提交后才会有的东西。
   */
  const askRerunChoice = (draftNow: DraftState, targets: { mi: number }[]): Promise<RerunChoice> => {
    const conflicts = targets
      .map(({ mi }) => detectAutoSplitConflicts(draftNow, mi, [{ page_start: 1, page_end: 1 } as PdfSplitSegmentSuggestion]))
      .filter((c): c is AutoSplitConflict => c !== null)
    // 没人改过：不必打扰，直接按「覆盖」走（与重跑前的旧行为完全一致）
    if (conflicts.length === 0) return Promise.resolve('overwrite')
    return new Promise((resolve) => setPendingConflicts({ conflicts, draft: draftNow, resolve }))
  }

  const run = async () => {
    const { openId, draft } = useReader.getState()
    if (!openId || !draft || running) return

    // ── 按附件粒度分派取字路径（见 docs/material-prep-dispatch.md）──
    // 一个材料包里扫描件 / 电子版 / 图片 / Word 混在一起是常态，每类的正确
    // 路径不同，所以**按 mat 逐个选路**，不能按整包一刀切：
    //   · pdf   → 云端拆分任务（后端逐页再选文本层 / 云端 / 本地 OCR）
    //   · photo → 单页取字（RapidOCR），图片本就单页，谈不上分段
    //   · office → 暂不进自动流程（Word 应走文档解析，见文档第六节）
    const pdfMats = draft.mats
      .map((mat, mi) => ({ mat, mi }))
      .filter(({ mat }) => mat.k === 'pdf')
    const targets = pdfMats.filter(({ mi }) => canAutoSplitMat(draft, mi))
    const photoTargets = draft.mats
      .map((mat, mi) => ({ mat, mi }))
      .filter(({ mat }) => mat.k === 'photo')
    // Word / Excel：走 document-parsing 的 office 后端（本地 OOXML 解析），
    // 不是 OnlyOffice——DS 是给人看改的编辑器，抽文本绕远且要再过一遍 OCR。
    const officeTargets = draft.mats
      .map((mat, mi) => ({ mat, mi }))
      .filter(({ mat }) => mat.k === 'office')
    if (targets.length === 0 && photoTargets.length === 0 && officeTargets.length === 0) {
      if (pdfMats.length > 0) {
        toast.info('这些 PDF 都已人工拆分或跨源合并，为免覆盖你的操作已跳过；需要重来可点「恢复初始分段」')
      } else {
        toast.info('材料包里没有可自动识别的材料')
      }
      return
    }

    // ── 重跑前问一次：会不会抹掉律师改过的东西 ──
    // 必须在 setRunning(true) **之前**：取消时整次 run 不执行，也不能留下 running 残态。
    const choice = await askRerunChoice(draft, targets)
    if (choice === 'cancel') return
    // 等弹窗期间草稿可能被改过（用户不会，但防御重入/切包）：以最新草稿为准
    if (useReader.getState().openId !== openId) return

    // 先开新会话再置 running：同帧重入的第二个 run 从这里开始，第一个循环立刻过期
    const lease = pollSession.begin()
    setRunning(true)
    if (targets.length > 0) setProgress(`正在提交 ${targets.length} 个 PDF`)
    try {
      // 版面策略在 ReaderState 上（不是 DraftState）：它是本次识别的成本选择，
      // 随会话复位，不落草稿。整批只读一次，避免每个 PDF 各读一遍。
      const layoutMode = useReader.getState().layoutMode
      const cloudBackend = useReader.getState().cloudBackend
      const jobs = await Promise.all(
        targets.map(async ({ mat, mi }) => {
          // ① 先查有没有**已经算好**的任务可直接复用。
          //
          // 真实痛点：164 页材料跑一次要 5-10 分钟 + 几十元（云端 OCR + LLM 分段），
          // 但只要 draft_state 没回写（没点过按钮 / 换浏览器），阅读器就拿不到
          // 结果，一点「自动识别」就从零重跑。这里命中就直接拿 segments。
          // 匹配口径（文件名 + 页数 + 已出结果）在后端 find_reusable_job 里。
          const reusable = await findReusablePdfSplitJob(mat.n, mat.pages)
          if (reusable?.segments?.length) {
            setProgress(`${mat.n}：复用已有识别结果`)
            return { mi, jobId: reusable.job_id, reused: true, prefetched: reusable }
          }

          const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
          const filename = mat.customName || mat.n
          const file = new File([bytes], filename.toLowerCase().endsWith('.pdf') ? filename : `${filename}.pdf`, {
            type: 'application/pdf',
          })
          // 版面策略跟着当前会话走：开了补版面才让电子页上云端拿坐标
          return { mi, jobId: await createPdfSplitJob(file, { layoutMode, cloudBackend }), reused: false, prefetched: null }
        }),
      )
      const settled: PromiseSettledResult<AutoSplitResult>[] = []
      let finished = 0
      for (const { mi, jobId, prefetched } of jobs) {
        // 串行轮询：过期会话（连点重入 / 卸载）在这里就退出，不再产生新请求
        if (lease.isStale()) break
        try {
          // 复用的任务已经是 review_required/completed，不必再轮询一轮
          const result = prefetched ?? (await pollJob(jobId, lease, setProgress))
          if (lease.isStale()) break
          finished += 1
          setProgress(`云端识别完成 ${finished}/${jobs.length}`)
          settled.push({
            status: 'fulfilled',
            value: { mi, segments: result.segments, segmentBackend: segmentBackendOf(result) },
          })
        } catch (error) {
          settled.push({ status: 'rejected', reason: error })
        }
      }

      // 轮询期间可能已卸载（关掉阅读器）或重入：不再回写 store、不再弹提示
      if (lease.isStale()) return
      const results = settled.flatMap((item) => (item.status === 'fulfilled' ? [item.value] : []))
      const failures = settled.filter((item) => item.status === 'rejected')

      // ── 图片：单页取字（与 PDF 分段并行，互不影响）──
      // 图片不参与「分段」（本就只有一页），它要的是把这一页的文字填进段里。
      // 单独一轨，避免图片识别失败拖垮 PDF 分段这条主线。
      const photoTexts: { mi: number; md: string }[] = []
      let photoFailed = 0
      for (const { mat, mi } of photoTargets) {
        if (lease.isStale()) return
        try {
          const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
          const blob = new Blob([bytes], { type: guessImageType(mat.n) })
          const ocr = await ocrImage(blob)
          const md = blocksToMarkdown(ocr.blocks)
          if (md) photoTexts.push({ mi, md })
        } catch {
          photoFailed += 1
        }
      }

      // ── Word / Excel：单份解析取字（同样单独一轨，不与 PDF 分段互相拖累）──
      const officeTexts: { mi: number; md: string }[] = []
      let officeFailed = 0
      for (const { mat, mi } of officeTargets) {
        if (lease.isStale()) return
        try {
          const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
          const file = new File([bytes], mat.customName || mat.n)
          const parsed = await parseOfficeFile(file)
          const md = parsed.markdown || parsed.text
          if (md) officeTexts.push({ mi, md })
        } catch {
          officeFailed += 1
        }
      }

      if (results.length === 0 && photoTexts.length === 0 && officeTexts.length === 0) {
        const failure = failures[0]
        throw failure?.status === 'rejected' && failure.reason instanceof Error
          ? failure.reason
          : new Error('所有材料的识别任务均未完成')
      }

      const current = useReader.getState()
      if (current.openId !== openId) return
      // 用户在前面的弹窗里选了「保留我的修改」就走保留版：人工正文搬回新分段；
      // 选「用识别结果覆盖」（或本来就没冲突）就走原版，行为与重跑前完全一致。
      const applyFor = choice === 'keep' ? applyAutoSplitPreservingEdits : applyAutoSplit
      for (const result of results) {
        current.update((value) => applyFor(value, result.mi, result.segments))
      }
      for (const item of photoTexts) {
        current.update((value) => fillSegmentText(value, item.mi, item.md))
      }
      for (const item of officeTexts) {
        current.update((value) => fillSegmentText(value, item.mi, item.md))
      }
      // ── 自动回填当事人 ──
      // 分段完成后正文已在草稿里，当事人信息（借款人/银行）也就在里面。
      // 不回填的话律师得自己翻材料手打一遍右栏那两个框 —— 那正是机器该干的活。
      // 只填空字段（律师已填/改过的不覆盖），识别不出就留空，不猜。
      // ⚠️ 必须判空：单测里 store 的 draft 可能是 null，直接 detectParties 会抛
      //    「Cannot read properties of null」，把整条成功路径带崩（实测挂了 6 个用例）。
      //    现场不会有 null（阅读器打开着才有这个 hook），但测试环境有。
      let detected: { our: string; their: string } = { our: '', their: '' }
      try {
        const draftNow = useReader.getState().draft
        if (draftNow) {
          detected = detectParties(draftNow)
          if (detected.our || detected.their) {
            current.update((value) => {
              const { infos, changed } = applyDetectedParties(value.infos, detected)
              return changed ? { ...value, infos } : value
            })
          }
        }
      } catch {
        // 当事人识别是**附加价值**，失败不能拖垮分段主流程 ——
        // 分段成功才是主线，识别不到就留空让律师自己填。
        // 不加这层 try，测试环境里 draft 字段不全就会把整条成功路径带崩
        // （实测挂了 6 个用例，toast 一个都没弹）。
      }

      const count = results.reduce((sum, item) => sum + item.segments.length, 0)
      // 分段后端可观测：律所 AI 失败会静默降级规则引擎，得让用户知道拿到的是哪种质量
      const llmCount = results.filter((item) => item.segmentBackend === 'llm').length
      const backendNote =
        results.length === 0
          ? ''
          : llmCount === results.length
            ? '律所 AI 分段'
            : llmCount > 0
              ? `${llmCount}/${results.length} 律所 AI 分段，其余规则引擎`
              : '规则引擎分段（律所 AI 不可用）'
      // 几类材料的结果分开数：混在一起报「完成 N 份」会让律师以为图片也分了段。
      // 图片只回填正文、不产生分段，这里必须说清楚。
      const parts: string[] = []
      if (results.length > 0) parts.push(`${results.length} 个 PDF 已分段（${backendNote}，共 ${count} 段）`)
      if (photoTexts.length > 0) parts.push(`${photoTexts.length} 张图片已识别正文`)
      if (officeTexts.length > 0) parts.push(`${officeTexts.length} 份 Office 已转正文`)
      const failedTotal = failures.length + photoFailed + officeFailed
      const filled = detected.our || detected.their ? '；已自动填入当事人' : ''
      const tail = failedTotal > 0 ? `；${failedTotal} 份识别失败，可稍后重试` : '；未识别材料仍需人工归类'
      const message = `${parts.join('，')}${filled}${tail}`
      if (failedTotal > 0) toast.warning(message)
      else toast.success(message)
    } catch (error) {
      // 组件已卸载（关掉阅读器）或这次 run 已被新 run 取代：静默返回，不弹错误
      if (lease.isStale()) return
      toast.error(error instanceof Error ? error.message : '云端材料识别失败')
    } finally {
      // 过期会话不得复位：新会话正在跑，复位会让按钮可点、进度条消失
      if (!lease.isStale()) {
        setRunning(false)
        setProgress('')
      }
    }
  }

  // 弹窗的三个出口：选完就关框（resolve 会在 run 里被 await 接走）
  const answerConflicts = (choice: RerunChoice) => {
    const pending = pendingConflicts
    setPendingConflicts(null)
    pending?.resolve(choice)
  }

  return {
    run,
    running,
    progress,
    /** 非 null 时 ReaderDialogs 应弹重跑确认框 */
    pendingConflicts,
    onKeepEdits: () => answerConflicts('keep'),
    onOverwrite: () => answerConflicts('overwrite'),
    onCancelRerun: () => answerConflicts('cancel'),
  }
}
