/**
 * OA 立案 · 常见失败原因与处理建议。
 *
 * ═══ 为什么失败原因要提前摆出来 ═══
 * 浏览器自动化失败时，后端只会回一句 error_message（「页面元素未找到」之类），
 * 律师看不懂也不知道下一步做什么，最常见的反应是反复点重试 —— 而
 * 「页面改版」「字段校验不通过」这两种重试一百次也不会好转，只会把 OA 账号
 * 试到被锁。所以把最近 30 天真实发生过的失败分类、次数、处置方式列清楚，
 * 并标出「系统会自动重试 1 次」与「必须人工处理」的区别。
 *
 * 演示态常量 `DEMO_OA_FAILURE_CAUSES`；真实实现应来自会话失败事件聚合。
 */

import { PageTable } from '../court/PageTable'
import { Pill } from '../ui'
import { DEMO_OA_FAILURE_CAUSES } from '../demo-data'

export function OAFailureCauses() {
  const autoCount = DEMO_OA_FAILURE_CAUSES.filter((f) => f.autoRetry).length

  return (
    <PageTable
      title="常见失败原因"
      hint={`近 30 天 · ${DEMO_OA_FAILURE_CAUSES.length} 类`}
      action={<Pill tone={autoCount ? 'green' : 'neutral'}>{autoCount} 类可自动重试</Pill>}
      head={
        <>
          <th className="w-[132px]">原因</th>
          <th className="w-[64px]">触发位置</th>
          <th className="w-[72px] text-right">近 30 天</th>
          <th className="w-[86px]">处置</th>
          <th>处理建议</th>
        </>
      }
    >
      {DEMO_OA_FAILURE_CAUSES.map((f) => (
        <tr key={f.cause} className="align-top">
          <td className="py-2 pl-5 pr-3 text-[12px] font-medium">{f.cause}</td>
          <td className="py-2 pr-3">
            <Pill>{f.stage}</Pill>
          </td>
          <td className="py-2 pr-3 text-right text-[11px] tabular-nums text-muted-foreground">{f.hits} 次</td>
          <td className="py-2 pr-3">
            <Pill tone={f.autoRetry ? 'green' : 'yellow'}>{f.autoRetry ? '自动重试' : '需人工'}</Pill>
          </td>
          <td className="py-2 pr-5 text-[11.5px] leading-[1.6] text-muted-foreground">{f.advice}</td>
        </tr>
      ))}
    </PageTable>
  )
}
