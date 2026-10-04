import { useCallback, useState } from 'react'

import { useQueryClient } from '@tanstack/react-query'

import { usePollSession, type PollLease } from '@/hooks/use-poll-session'

import {
  getParseTaskTask,
  parseDocument,
  DOC_PARSE_MAX_POLLS,
  DOC_PARSE_POLL_MS,
  parseHistoryKeys,
  type ParseDocumentIn,
  type ParseOutcome,
} from '../../api'

/** 解析流程的阶段：idle 未开始 / submitting 提交中 / polling 云端轮询中 / done 结束 */
export type ParsePhase = 'idle' | 'submitting' | 'polling' | 'done'

/** 提示用户当前在等什么（本地后端同步返回，云端后端要轮询） */
const PHASE_HINT: Record<ParsePhase, string> = {
  idle: '',
  submitting: '正在上传并提交解析…',
  polling: '云端解析中，通常 5-30 秒…',
  done: '',
}

/**
 * `not_found` 的宽限轮数。
 *
 * django-q 的任务有一段「空窗期」：worker 把任务从队列摘下来、到写入 Task 表有
 * ~1-3 秒间隔；这段时间 OrmQ 和 Task 两张表里都查不到它，查询端点只能返回
 * not_found（见后端 tasking/query.py）。实测云端解析全程 3-5 秒，2 秒一轮的
 * 首次轮询大概率正好落进这段空窗——若把 not_found 当场判死，用户会看到
 * 「任务不存在」而云端其实正在解析，属于误报失败。
 * 所以连续 not_found 宽限 30 秒后才认定任务真的丢了（多半是 worker 未运行）。
 */
const NOT_FOUND_GRACE_POLLS = 15

export interface DocParseState {
  phase: ParsePhase
  hint: string
  outcome: ParseOutcome | null
}

export interface UseDocParseResult extends DocParseState {
  /** 提交解析：本地后端同步返回结果，云端后端返回 task_id 后内部轮询到出结果 */
  submit: (file: File, opts: ParseDocumentIn) => Promise<void>
  /** 清空上一次结果（换了文件就调它） */
  reset: () => void
}

/**
 * 文档解析流程编排：提交 →（同步直接出结果 | 异步轮询到终态）。
 *
 * 轮询用 setTimeout 串行而非 interval，避免上一轮请求还没回就打下一轮；
 * 重入与卸载经 usePollSession 的会话号守卫处理——旧实现里 cancelled ref
 * 只在卸载置位，换文件重提交时正在 await 的旧循环停不下来，会把旧任务的
 * 终态写进 state 覆盖新提交（详见 use-poll-session.ts 头注释）。
 */
export function useDocParse(): UseDocParseResult {
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<ParsePhase>('idle')
  const [outcome, setOutcome] = useState<ParseOutcome | null>(null)
  const pollSession = usePollSession()

  /** 写终态并失效解析历史列表：这条新记录到终态才完整落库，旧缓存的历史里看不到它 */
  const finish = useCallback(
    (o: ParseOutcome | null) => {
      setOutcome(o)
      setPhase('done')
      void queryClient.invalidateQueries({ queryKey: parseHistoryKeys.all })
    },
    [queryClient],
  )

  const reset = useCallback(() => {
    // 只失效会话：正在跑的轮询会自检退出，不再打接口、不再写 state
    pollSession.invalidate()
    setOutcome(null)
    setPhase('idle')
  }, [pollSession])

  /** 轮询云端任务到终态；lease 由 submit 签发，重提交/卸载后旧循环即刻自检退出 */
  const pollTask = useCallback(async (taskId: string, lease: PollLease) => {
    let notFoundStreak = 0
    for (let i = 0; i < DOC_PARSE_MAX_POLLS; i++) {
      if (lease.isStale()) return
      try {
        const s = await getParseTaskTask(taskId)
        if (lease.isStale()) return
        if (s.status === 'success' || s.status === 'failure') {
          finish(s.outcome)
          return
        }
        if (s.status === 'not_found') {
          notFoundStreak++
          if (notFoundStreak >= NOT_FOUND_GRACE_POLLS) {
            finish({
              ok: false,
              markdown: '',
              text: '',
              method: null,
              error: '解析任务排队后没有执行起来——多为后台 worker 未运行，可到「解析任务」查看',
              metadata: {},
            })
            return
          }
          // 仍在宽限期内：任务可能刚被 worker 摘走还没落库，继续等
        } else {
          // 只要查到 pending / running 就说明任务活着，清零宽限计数
          notFoundStreak = 0
        }
      } catch {
        if (lease.isStale()) return
        // 单轮查询失败不当场判死——云端任务还在跑，后端可能只是被瞬时打断，继续下一轮
      }
      await lease.sleep(DOC_PARSE_POLL_MS)
    }
    if (lease.isStale()) return
    finish({
      ok: false,
      markdown: '',
      text: '',
      method: null,
      error: '解析超时（超过 5 分钟仍无结果），请到后台「解析任务」查看',
      metadata: {},
    })
  }, [finish])

  const submit = useCallback(
    async (file: File, opts: ParseDocumentIn) => {
      // 先开新会话再清 state：旧任务「正在 await 网络」的轮询循环从此失效，
      // 不会再把旧终态写回来覆盖本次提交
      const lease = pollSession.begin()
      setOutcome(null)
      setPhase('submitting')
      try {
        const { taskId, outcome: sync } = await parseDocument(file, opts)
        // 上传期间可能重提交/卸载：过期会话的后续 state 一律不写
        if (lease.isStale()) return
        if (taskId) {
          setPhase('polling')
          await pollTask(taskId, lease)
          return
        }
        finish(sync)
      } catch {
        if (lease.isStale()) return
        finish({
          ok: false,
          markdown: '',
          text: '',
          method: null,
          error: '提交解析失败，请检查文件格式或稍后重试',
          metadata: {},
        })
      }
    },
    [pollSession, pollTask, finish],
  )

  return { phase, outcome, hint: PHASE_HINT[phase], submit, reset }
}
