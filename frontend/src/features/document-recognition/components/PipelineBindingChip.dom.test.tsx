// @vitest-environment jsdom
/**
 * 旁线（法院短信）识别任务的只读案件 chip 测试（jsdom）。
 *
 * 这个 chip 的唯一职责是「把绑定状态说清楚，且**不给**换选入口」：
 * 法院短信第一轮已经把案件/案件日志定死，日期候选会挂在那条日志上。
 * 若这里露出一个「换案件」的入口，用户改完看到的是原案件的日志锚点——
 * 日期写到了自己以为之外的地方。所以「不渲染任何可交互元素」是契约的一部分，
 * 单独断言，不靠视觉评审保证。
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PipelineBindingChip } from './PipelineBindingChip'
import type { TaskOut } from '../types'

function task(binding: Record<string, unknown> | null): TaskOut {
  return { task_id: 9, binding } as unknown as TaskOut
}

describe('PipelineBindingChip：已绑定', () => {
  it('显示绑定的案件名', () => {
    const { container } = render(
      <PipelineBindingChip task={task({ success: true, case_id: 3001, case_name: '谭某某借款纠纷' })} />,
    )
    expect(container.textContent).toContain('已由法院短信绑定：谭某某借款纠纷')
    expect(container.textContent).toContain('日期将写入该案件日志')
    container.remove()
  })

  it('后端没给案件名时退回案件号（不能显示成「已绑定：」后面空着）', () => {
    const { container } = render(
      <PipelineBindingChip task={task({ success: true, case_id: 3001, case_name: '' })} />,
    )
    expect(container.textContent).toContain('已由法院短信绑定：案件 3001')
    container.remove()
  })

  it('只读：不渲染任何按钮或链接（给出口就是给假改绑）', () => {
    const { container } = render(
      <PipelineBindingChip task={task({ success: true, case_id: 3001, case_name: '谭某某借款纠纷' })} />,
    )
    expect(container.querySelectorAll('button, a, input, select')).toHaveLength(0)
    container.remove()
  })
})

describe('PipelineBindingChip：未绑定', () => {
  it('明确告知「不会写进任何案件日志」，且不静默降级成已绑定样式', () => {
    const { container } = render(<PipelineBindingChip task={task(null)} />)
    expect(container.textContent).toContain('这条识别任务没有关联到案件')
    expect(container.textContent).toContain('不会写进任何案件日志')
    expect(container.textContent).not.toContain('已由法院短信绑定')
    container.remove()
  })
})
