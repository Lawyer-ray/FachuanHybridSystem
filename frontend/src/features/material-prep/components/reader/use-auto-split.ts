import { useState } from 'react'
import { toast } from 'sonner'
import { fetchAttachmentBytes, createPdfSplitJob, getPdfSplitJob } from '../../api'
import { applyAutoSplit, canAutoSplitMat } from '../../draft'
import { useReader } from '../../store'

const POLL_DELAY_MS = 2000
const POLL_LIMIT = 420

export function useAutoSplit() {
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState('')

  const run = async () => {
    const { openId, draft } = useReader.getState()
    if (!openId || !draft || running) return

    const targets = draft.mats
      .map((mat, mi) => ({ mat, mi }))
      .filter(({ mat, mi }) => mat.k === 'pdf' && canAutoSplitMat(draft, mi))
    if (targets.length === 0) {
      toast.info('没有可自动识别的 PDF；含人工拆分或跨源合并的材料会保留原样')
      return
    }

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
      let finished = 0
      const settled = await Promise.allSettled(
        jobs.map(async ({ mi, jobId }) => {
          const result = await pollJob(jobId)
          finished += 1
          setProgress(`云端识别完成 ${finished}/${jobs.length}`)
          return { mi, segments: result.segments }
        }),
      )

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
      if (failures.length) {
        toast.warning(`${results.length} 个 PDF 已写入草稿，${failures.length} 个识别失败，可稍后重试`)
      } else {
        toast.success(`云端识别完成，已将 ${count} 个候选分段写入草稿；未识别材料仍需人工归类`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '云端材料识别失败')
    } finally {
      setRunning(false)
      setProgress('')
    }
  }

  return { run, running, progress }
}

async function pollJob(jobId: string) {
  for (let attempt = 0; attempt < POLL_LIMIT; attempt++) {
    const job = await getPdfSplitJob(jobId)
    if (job.status === 'review_required' || job.status === 'completed') return job
    if (job.status === 'failed' || job.status === 'cancelled') {
      throw new Error(job.error_message || `PDF 拆分任务${job.status === 'failed' ? '失败' : '已取消'}`)
    }
    await new Promise((resolve) => window.setTimeout(resolve, POLL_DELAY_MS))
  }
  throw new Error('云端识别等待超时，请稍后重试')
}
