import { useCallback, useState } from 'react'

import { usePollSession, type PollLease } from '@/hooks/use-poll-session'

import { createConverterJob, getConverterJob, type ConverterJob } from '../../api'

/** 轮询节奏与上限：2s 一次，5 分钟仍没结束就转「后台继续」 */
const DOC_CONVERTER_POLL_MS = 2_000
const DOC_CONVERTER_MAX_POLLS = 150

/** 转换任务编排阶段：idle 未提交 / running 轮询中 / success 有产物 / error 失败 / timeout 后台继续 */
export type ConverterPhase = 'idle' | 'running' | 'success' | 'error' | 'timeout'

export interface UseConverterJobResult {
  phase: ConverterPhase
  jobId: string | null
  /** 最近一次任务详情（进度条 / 结果列表渲染用） */
  job: ConverterJob | null
  error: string | null
  /** 提交并轮询到终态（终态由 phase 表达） */
  submit: (files: File[]) => Promise<void>
  /** timeout 后继续等待（只恢复轮询，不重跑后端任务） */
  resume: () => void
}

/**
 * DOC 转 DOCX 任务编排：提交 → 轮询 job 到终态（completed / failed / 计数收敛）。
 *
 * 从 DocConverterCard 内联轮询抽出：旧实现 cancelled ref 只在卸载置位、共享单个
 * timer ref——换文件重提交时「正在 await 网络」的旧循环停不下来，旧 job 的终态
 * 会覆盖新提交（详见 use-poll-session.ts 头注释）；抽出的 hook 走会话号守卫。
 * 卡片只保留纯 UI 编排（弹窗 / 文件选择 / 复制下载）。
 */
export function useConverterJob(): UseConverterJobResult {
  const [phase, setPhase] = useState<ConverterPhase>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<ConverterJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollSession = usePollSession()

  /** 轮询 job 到终态；lease 由 submit/resume 签发，失效后旧循环自检退出 */
  const poll = useCallback(async (id: string, lease: PollLease) => {
    for (let i = 0; i < DOC_CONVERTER_MAX_POLLS; i++) {
      if (lease.isStale()) return
      try {
        const j = await getConverterJob(id)
        if (lease.isStale()) return
        setJob(j)
        // 终态判定：显式 completed/failed，或计数收敛（后端中途不再更新 status 也能收尾）
        const settled = j.total > 0 && j.done + j.failed >= j.total
        if (j.status === 'completed' || j.status === 'failed' || settled) {
          setPhase(j.done > 0 ? 'success' : 'error')
          setError(j.done > 0 ? null : '全部文件转换失败，请确认上传的是 .doc 文件')
          return
        }
      } catch {
        if (lease.isStale()) return
        // 查询进度失败当场判死（任务本身多半还在，可稍后从历史记录回来下载）
        setPhase('error')
        setError('查询转换进度失败，可稍后重试')
        return
      }
      await lease.sleep(DOC_CONVERTER_POLL_MS)
    }
    if (lease.isStale()) return
    // 5 分钟仍在跑：不判失败，后台会继续；用户可「继续等待」或稍后回来下载
    setPhase('timeout')
  }, [])

  const submit = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return
      // 先开新会话再清 state：旧 job「正在 await 网络」的轮询从此失效
      const lease = pollSession.begin()
      setPhase('running')
      setJob(null)
      setError(null)
      try {
        const id = await createConverterJob(files)
        if (lease.isStale()) return
        setJobId(id)
        await poll(id, lease)
      } catch (e) {
        if (lease.isStale()) return
        setError(e instanceof Error ? e.message : '提交转换任务失败')
        setPhase('error')
      }
    },
    [poll, pollSession],
  )

  const resume = useCallback(() => {
    if (jobId == null) return
    setPhase('running')
    void poll(jobId, pollSession.begin())
  }, [jobId, poll, pollSession])

  return { phase, jobId, job, error, submit, resume }
}
