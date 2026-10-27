// @vitest-environment jsdom
/**
 * components/shared/AsyncState（三态块）单测（jsdom）。
 *
 * 这三块是 35 处手写副本的唯一来源，锁住的是「文案默认值 + 错误文案抽取」：
 * ErrorBlock 必须把 ky/Timeout/普通 Error 都交给 errMessage 抽中文，抽不到才回落
 * fallback——否则服务端故障又会被渲染成一句笼统的兜底文案。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EmptyBlock, ErrorBlock, LoadingBlock } from './AsyncState'

describe('LoadingBlock', () => {
  it('默认文案「加载中…」并带转圈图标', () => {
    const { container } = render(<LoadingBlock />)
    expect(screen.getByText('加载中…')).toBeTruthy()
    expect(container.querySelector('.animate-spin')).toBeTruthy()
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('自定义文案与 className 透传', () => {
    const { container } = render(<LoadingBlock text="正在打开材料包" className="py-2" />)
    expect(screen.getByText('正在打开材料包')).toBeTruthy()
    expect(container.firstElementChild?.className).toContain('py-2')
  })
})

describe('EmptyBlock', () => {
  it('渲染文案，无 icon/action 时不渲染多余槽位', () => {
    const { container } = render(<EmptyBlock>暂无历史记录</EmptyBlock>)
    expect(screen.getByText('暂无历史记录')).toBeTruthy()
    expect(container.querySelectorAll('div')).toHaveLength(2)
  })

  it('icon 与 action 各自渲染', () => {
    render(
      <EmptyBlock icon={<svg data-testid="empty-icon" />} action={<button type="button">上传材料</button>}>
        还没有材料
      </EmptyBlock>,
    )
    expect(screen.getByTestId('empty-icon')).toBeTruthy()
    expect(screen.getByRole('button', { name: '上传材料' })).toBeTruthy()
  })
})

describe('ErrorBlock', () => {
  it('普通 Error 显示其 message', () => {
    render(<ErrorBlock error={new Error('网线被拔了')} />)
    expect(screen.getByRole('alert').textContent).toContain('网线被拔了')
  })

  it('后端错误体里的 message 优先于 fallback', () => {
    render(<ErrorBlock error={{ data: { message: '材料包不存在' } }} />)
    expect(screen.getByRole('alert').textContent).toContain('材料包不存在')
  })

  it('无可读文案时回 fallback（默认「加载失败，请重试」）', () => {
    render(<ErrorBlock error={null} />)
    expect(screen.getByRole('alert').textContent).toContain('加载失败，请重试')
  })

  it('给了 onRetry 才渲染「重新加载」，点击回调一次', () => {
    const onRetry = vi.fn()
    render(<ErrorBlock error={new Error('boom')} onRetry={onRetry} />)
    const btn = screen.getByRole('button', { name: '重新加载' })
    fireEvent.click(btn)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('没有 onRetry 时不渲染重试按钮', () => {
    render(<ErrorBlock error={new Error('boom')} />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
