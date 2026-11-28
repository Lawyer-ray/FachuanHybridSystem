/**
 * 试跑工作台（审批面板里的一块）：选注入模式 → 真跑一轮 → 把模型回复和「它实际看到了
 * 什么」摊给审批人。四条判据都是「不写清就会让人做错决定」那一类：
 *
 * 1. **三档模式各自说明「验的是哪一层」**：内联全文验指令语义，真索引验自主发现。不写
 *    清楚，审批人会把一次通过的试跑当成上线保证——那轮根本没验模型会不会自己想到读它
 *    （后端 `services/skills/trial.py` 的模块注释同此口径）。
 * 2. **等待态独立**：3–45 秒的慢端点，沿用列表那种「点完就回来」的交互会让人以为没点
 *    上，所以有 elapsed 秒表 +「模型正在读你的技能」+ 可取消。
 * 3. **`model` 为空时整项不显示**：渲染成 "null" 比不显示更糟，审批人会以为那是模型名。
 * 4. **`tool_errors` 非空要说清后果**：模型没取到全文时，这一轮的回复不是「技能的效果」。
 *
 * 额度只在明确拿到 `remaining === 0` 时才拦：`trial-quota` 是与后端并行落地的 ★ 端点，
 * 旧后端 404 时禁死按钮会让整个功能在升级前不可用。
 */

import { useQuery } from '@tanstack/react-query'
import { HTTPError } from 'ky'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'

import { InjectedBlock, ToolCallList, ToolErrorList, TrialMeta } from './SkillTrialResult'

import { fetchAgentSkillTrialQuota, runAgentSkillTrial } from '../../skill-api'
import type {
  AgentSkill,
  AgentSkillTrialMode,
  AgentSkillTrialResult,
} from '../../skill-types'

/** 额度缓存键：与技能清单/配额分开，技能写动作不该顺手让额度条重拉 */
const TRIAL_QUOTA_QUERY_KEY = ['agent-skill-trial-quota'] as const

/** 秒表刷新间隔：250ms 只为让「1s → 2s」跳得跟得上，不必更密 */
const ELAPSED_TICK_MS = 250

/** 三档模式：label 直接带「验的是哪一层」，hint 说明这一档到底在验什么 */
const TRIAL_MODE_OPTIONS: { value: AgentSkillTrialMode; label: string; hint: string }[] = [
  { value: 'auto', label: '自动', hint: '已发布的技能按真实索引验，未发布的按内联全文验' },
  { value: 'inline', label: '内联全文（验指令语义）', hint: '模型直接读全文——验的是这条指令写得好不好' },
  { value: 'index', label: '真索引（验自主发现）', hint: '只给名字与描述，模型必须自己调 get_agent_skill 取全文' },
]

/** 一次试跑的界面状态：互斥的几档，不留「既在跑又有结果」这种组合 */
type TrialRun =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'result'; result: AgentSkillTrialResult }
  | { kind: 'failed'; message: string }
  | { kind: 'cancelled' }

/** 额度恢复时间：只到分钟；解析不了就原样给，不猜时区（猜错会差一天） */
function resetAtText(resetAt: string | undefined): string {
  if (!resetAt) return ''
  const parsed = new Date(resetAt)
  if (Number.isNaN(parsed.getTime())) return resetAt
  return parsed.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** 额度一行文案：取不到额度时不说「0 次」——那会把「不知道」读成「用完了」 */
function quotaText(state: { loading: boolean; failed: boolean; remaining: number | undefined }): string {
  if (state.loading) return '正在查今日额度…'
  if (state.failed) return '今日额度取不到（不影响试跑）'
  return state.remaining === undefined ? '' : `今日剩余 ${state.remaining} 次`
}

/** 失败文案：超时单独说——「等太久」和「服务端报错」的下一步动作完全不同 */
function failureMessage(error: unknown): string {
  const name = error && typeof error === 'object' ? (error as { name?: unknown }).name : undefined
  if (name === 'TimeoutError') return '试跑超时：模型可能正在跑一个长工具。可以重试，或把问题缩短后再试。'
  return errMessage(error, '试跑失败，请稍后重试')
}

/** 一轮结果：失败只给原因；成功给正文 + 元信息 + 工具面 + 实际注入 */
function TrialResultView({ result }: { result: AgentSkillTrialResult }) {
  if (!result.ok) {
    // 服务端把原因放在 `error` 字符串里（不是 HTTP 错误体）：包成 Error 走同一个文案抽取
    return (
      <p
        role="alert"
        className="mt-2 rounded-[9px] border border-status-red/40 bg-status-red-bg px-2.5 py-2 text-[11px] leading-relaxed text-destructive"
      >
        {errMessage(new Error(result.error), '试跑失败，服务端没有给出原因')}
      </p>
    )
  }
  const toolErrors = result.tool_errors ?? []
  return (
    <div className="mt-2 rounded-[9px] border border-border bg-card px-2.5 py-2">
      <TrialMeta result={result} />
      <p className="mt-1 max-h-[34vh] overflow-y-auto whitespace-pre-wrap text-[11.5px] leading-relaxed text-foreground">
        {result.text || '（模型没有返回正文）'}
      </p>
      {result.tool_calls.length > 0 ? (
        <div className="mt-1.5">
          <ToolCallList calls={result.tool_calls} />
        </div>
      ) : (
        <p className="mt-1 text-[10.5px] text-muted-foreground">
          本轮没有调用任何工具{result.mode === 'inline' ? '（内联全文模式下不需要取全文）' : ''}。
        </p>
      )}
      {toolErrors.length > 0 ? <ToolErrorList errors={toolErrors} /> : null}
      <InjectedBlock text={result.injected} />
    </div>
  )
}

export function SkillTrialPanel({ skill }: { skill: AgentSkill }) {
  const [mode, setMode] = useState<AgentSkillTrialMode>('auto')
  const [question, setQuestion] = useState('')
  const [run, setRun] = useState<TrialRun>({ kind: 'idle' })
  const [elapsedMs, setElapsedMs] = useState(0)
  const [quotaNotice, setQuotaNotice] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const quotaQuery = useQuery({
    queryKey: TRIAL_QUOTA_QUERY_KEY,
    queryFn: ({ signal }) => fetchAgentSkillTrialQuota(signal),
    staleTime: 60_000,
  })
  const quota = quotaQuery.data
  const exhausted = quota?.remaining === 0
  // 草稿与已下线都不在运行时索引里（服务端对 index 模式回 422）：提前禁用才看得见原因
  const blockedIndex = skill.status !== 'active'
  const running = run.kind === 'running'

  // 秒表只在跑的时候开：结束时 effect 清理自动停，elapsedMs 由 startTrial 归零
  useEffect(() => {
    if (!running) return
    const startedAt = Date.now()
    const timer = window.setInterval(() => setElapsedMs(Date.now() - startedAt), ELAPSED_TICK_MS)
    return () => window.clearInterval(timer)
  }, [running])

  // 离开面板即断开在途请求：不让一个几十秒的试跑在后台白烧额度
  useEffect(() => () => abortRef.current?.abort(), [])

  const startTrial = async () => {
    if (running) return
    const controller = new AbortController()
    abortRef.current = controller
    setQuotaNotice('')
    setElapsedMs(0)
    setRun({ kind: 'running' })
    const trimmed = question.trim()
    // 留空 = 服务端默认探针问法：那条问法刻意要求「先原样复述第一条要求」，比前端
    // 随手编一句更能验出模型到底读没读到正文
    const input = { mode, ...(trimmed ? { question: trimmed } : {}) }
    try {
      setRun({ kind: 'result', result: await runAgentSkillTrial(skill.key, input, controller.signal) })
    } catch (error) {
      if (controller.signal.aborted) {
        setRun({ kind: 'cancelled' })
      } else if (error instanceof HTTPError && error.response.status === 429) {
        // 429 的文案里带 limit 与恢复时间：就地提示 + 刷新额度（不 toast，审批人还要回头改问题）
        setQuotaNotice(errMessage(error, '今日试跑额度已用完'))
        setRun({ kind: 'idle' })
        await quotaQuery.refetch()
      } else {
        setRun({ kind: 'failed', message: failureMessage(error) })
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  const cancelTrial = () => abortRef.current?.abort()

  return (
    <section aria-label="试跑" className="mt-3 rounded-[9px] border border-border bg-card px-2.5 py-2">
      <header className="flex flex-wrap items-baseline gap-1.5">
        <h3 className="text-[11.5px] font-[650] text-foreground">试跑：让模型真读一遍</h3>
        <span className="text-[10.5px] text-muted-foreground">不写会话历史、不可能改任何东西，可以反复跑</span>
      </header>

      <div role="radiogroup" aria-label="试跑模式" className="mt-2 space-y-1">
        {TRIAL_MODE_OPTIONS.map((option) => {
          const blocked = option.value === 'index' && blockedIndex
          const active = mode === option.value
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={blocked || running}
              onClick={() => setMode(option.value)}
              className={`block w-full rounded-[9px] border px-2 py-1 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                active ? 'border-ring bg-secondary' : 'border-border hover:bg-secondary/60'
              }`}
            >
              <span className="text-[11.5px] font-medium text-foreground">{option.label}</span>
              <span className="mt-0.5 block text-[10.5px] leading-relaxed text-muted-foreground">{option.hint}</span>
              {blocked ? (
                <span className="mt-0.5 block text-[10.5px] leading-relaxed text-status-yellow">
                  这条还没发布：先发布才能验证自主发现
                </span>
              ) : null}
            </button>
          )
        })}
      </div>

      <label htmlFor="skill-trial-question" className="mt-2 block text-[11px] font-[650] text-foreground">
        问题（可选）
      </label>
      <Textarea
        id="skill-trial-question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        disabled={running}
        placeholder="留空则用默认探针：先原样输出第一条要求，再说明你会怎么做"
        className="mt-1 min-h-[52px] text-[12px]"
      />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {running ? (
          <Button variant="outline" size="sm" className="h-7 px-3 text-[11px]" onClick={cancelTrial}>
            取消
          </Button>
        ) : (
          <Button size="sm" className="h-7 px-3 text-[11px]" disabled={exhausted} onClick={() => void startTrial()}>
            运行试跑
          </Button>
        )}
        <span className="text-[10.5px] text-muted-foreground">
          {quotaText({ loading: quotaQuery.isLoading, failed: quotaQuery.isError, remaining: quota?.remaining })}
        </span>
      </div>

      {exhausted ? (
        <p className="mt-1 text-[10.5px] leading-relaxed text-status-yellow">
          今日额度已用完{quota?.limit === undefined ? '' : `（每天 ${quota.limit} 次）`}
          {resetAtText(quota?.reset_at) ? `，${resetAtText(quota?.reset_at)} 恢复` : ''}。额度用完不影响审批：通过 / 驳回照常可用。
        </p>
      ) : null}

      {quotaNotice ? (
        <p
          role="alert"
          className="mt-1 rounded-[9px] border border-status-yellow/50 bg-status-yellow-bg px-2.5 py-1.5 text-[11px] leading-relaxed text-foreground"
        >
          {quotaNotice}
        </p>
      ) : null}

      {running ? (
        <div role="status" aria-live="polite" className="mt-2 rounded-[9px] border border-border bg-secondary px-2.5 py-2">
          <p className="text-[11.5px] text-foreground">
            模型正在读你的技能…已等{' '}
            <span data-testid="trial-elapsed" className="font-mono">
              {Math.floor(elapsedMs / 1000)}s
            </span>
          </p>
          <p className="mt-0.5 text-[10.5px] leading-relaxed text-muted-foreground">
            这一轮要真起一个模型读全文再回答，通常 3–45 秒；卡住可以点「取消」，取消后改了问题可以重跑。
          </p>
        </div>
      ) : null}

      {run.kind === 'result' ? <TrialResultView result={run.result} /> : null}
      {run.kind === 'failed' ? (
        <p
          role="alert"
          className="mt-2 rounded-[9px] border border-status-red/40 bg-status-red-bg px-2.5 py-2 text-[11px] leading-relaxed text-destructive"
        >
          {run.message}
        </p>
      ) : null}
      {run.kind === 'cancelled' ? (
        <p className="mt-2 text-[10.5px] leading-relaxed text-muted-foreground">
          已取消这次试跑：模型回复没保存，改了问题可以重跑。
        </p>
      ) : null}
    </section>
  )
}
