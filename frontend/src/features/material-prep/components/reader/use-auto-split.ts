import { useState } from 'react'
import { toast } from 'sonner'
import { fetchAttachmentBytes, createPdfSplitJob, getPdfSplitJob } from '../../api'
import { applyAutoSplit, canAutoSplitMat } from '../../draft'
import { useReader } from '../../store'
import type { PdfSplitSegmentSuggestion } from '../../types'
import { usePollSession, type PollLease } from '@/hooks/use-poll-session'

const POLL_DELAY_MS = 2000
const POLL_LIMIT = 420

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
  const pollSession = usePollSession()

  const run = async () => {
    const { openId, draft } = useReader.getState()
    if (!openId || !draft || running) return

    const pdfMats = draft.mats
      .map((mat, mi) => ({ mat, mi }))
      .filter(({ mat }) => mat.k === 'pdf')
    const targets = pdfMats.filter(({ mi }) => canAutoSplitMat(draft, mi))
    if (targets.length === 0) {
      if (pdfMats.length === 0) {
        toast.info('材料包里没有 PDF —— 云端识别只支持 PDF，图片 / Word 等请人工归类')
      } else {
        toast.info('这些 PDF 都已人工拆分或跨源合并，为免覆盖你的操作已跳过；需要重来可点「恢复初始分段」')
      }
      return
    }

    // 先开新会话再置 running：同帧重入的第二个 run 从这里开始，第一个循环立刻过期
    const lease = pollSession.begin()
    setRunning(true)
    setProgress(`正在提交 ${targets.length} 个 PDF`)
    try {
      const jobs = await Promise.all(
        targets.map(async ({ mat, mi }) => {
          const bytes = await fetchAttachmentBytes(openId, mat.partIndex)
          const filename = mat.customName || mat.n
          const file = new File([bytes], filename.toLowerCase().endsWith('.pdf') ? filename : `${filename}.pdf`, {
            type: 'application/pdf',
          })
          return { mi, jobId: await createPdfSplitJob(file) }
        }),
      )
      const settled: PromiseSettledResult<AutoSplitResult>[] = []
      let finished = 0
      for (const { mi, jobId } of jobs) {
        // 串行轮询：过期会话（连点重入 / 卸载）在这里就退出，不再产生新请求
        if (lease.isStale()) break
        try {
          const result = await pollJob(jobId, lease)
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
      if (results.length === 0) {
        const failure = failures[0]
        throw failure?.status === 'rejected' && failure.reason instanceof Error
          ? failure.reason
          : new Error('所有 PDF 识别任务均未完成')
      }

      const current = useReader.getState()
      if (current.openId !== openId) return
      for (const result of results) {
        current.update((value) => applyAutoSplit(value, result.mi, result.segments))
      }
      const count = results.reduce((sum, item) => sum + item.segments.length, 0)
      // 分段后端可观测：律所 AI 失败会静默降级规则引擎，得让用户知道拿到的是哪种质量
      const llmCount = results.filter((item) => item.segmentBackend === 'llm').length
      const backendNote = llmCount === results.length ? '律所 AI 分段' : llmCount > 0 ? `${llmCount}/${results.length} 律所 AI 分段，其余规则引擎` : '规则引擎分段（律所 AI 不可用）'
      if (failures.length) {
        toast.warning(`${results.length} 个 PDF 已写入草稿（${backendNote}），${failures.length} 个识别失败，可稍后重试`)
      } else {
        toast.success(`云端识别完成（${backendNote}），已将 ${count} 个候选分段写入草稿；未识别材料仍需人工归类`)
      }
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

  return { run, running, progress }
}

/** 分段来源标记：summary 是自由字典，取不到就当规则引擎（保守，不谎报 AI 分段） */
function segmentBackendOf(job: { summary: Record<string, unknown> }): string {
  const backend = job.summary.segment_backend
  return typeof backend === 'string' ? backend : ''
}

async function pollJob(jobId: string, lease: PollLease) {
  for (let attempt = 0; attempt < POLL_LIMIT; attempt++) {
    if (lease.isStale()) throw new Error('已取消')
    const job = await getPdfSplitJob(jobId)
    if (job.status === 'review_required' || job.status === 'completed') return job
    if (job.status === 'failed' || job.status === 'cancelled') {
      throw new Error(job.error_message || `PDF 拆分任务${job.status === 'failed' ? '失败' : '已取消'}`)
    }
    await lease.sleep(POLL_DELAY_MS)
  }
  throw new Error('云端识别等待超时，请稍后重试')
}
