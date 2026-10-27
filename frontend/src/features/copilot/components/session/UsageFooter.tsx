/**
 * 个人本月用量摘要（P1-2）：失败率非零才显示，保持一行克制。
 *
 * 从 SessionSidebar 拆出（后者超软红线）；自己取 query，对外零 props。
 */

import { useQuery } from '@tanstack/react-query'

import { getUsageSummary } from '../../api'

export function UsageFooter() {
  const { data } = useQuery({
    queryKey: ['copilot', 'usage', 30],
    queryFn: () => getUsageSummary(30),
    staleTime: 300_000,
    retry: false,
  })
  if (!data || data.runs === 0) return null
  const tokens = data.total_tokens >= 10000 ? `${(data.total_tokens / 1000).toFixed(1)}k` : String(data.total_tokens)
  const errPct = data.error_rate > 0 ? `${(data.error_rate * 100).toFixed(data.error_rate < 0.1 ? 1 : 0)}%` : ''
  const avg = data.avg_duration_ms >= 1000 ? `${(data.avg_duration_ms / 1000).toFixed(1)}s` : `${data.avg_duration_ms}ms`
  return (
    <div
      className="mt-auto flex-none border-t border-border px-3 py-2 text-[11px] leading-relaxed text-muted-foreground"
      title={
        `近 30 天：${data.runs} 轮（完成 ${data.ok_runs} / 出错 ${data.error_runs} / 中止 ${data.cancelled_runs}），` +
        `输入 ${data.input_tokens} + 输出 ${data.output_tokens} tokens，工具调用 ${data.tool_calls} 次`
      }
    >
      近 30 天 {data.runs} 轮 · {tokens} tokens · 均耗 {avg}
      {errPct && <span className="text-destructive/80"> · 失败 {errPct}</span>}
    </div>
  )
}
