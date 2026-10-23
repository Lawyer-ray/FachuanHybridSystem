// @vitest-environment jsdom
/**
 * 工具区共用零件测试：StageStrip / StageSteps / HistoryParts / HistoryError / shared。
 *
 * 这些是纯展示组件，重点锁定分支语义：
 * - 阶段条的三态（done / active / failed）与「进行中…/失败」标注
 * - 分页在首末页禁用
 * - ToolShell 的拖放过滤：按 accept 后缀匹配、全不匹配时提示
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

import { toast } from 'sonner'

import { HistoryError } from './history/HistoryError'
import { HistoryButton, HistoryHeader, HistoryPager } from './history/HistoryParts'
import { StageSteps } from './dialog/StageSteps'
import { StageStrip } from './dialog/StageStrip'
import { FilePicker, Spinner, ToolShell } from './shared'

const STEPS = ['解析', '下载', '匹配'] as const

describe('StageStrip（横向紧凑进度条）', () => {
  it('按 current 区分已完成 / 进行中 / 未开始', () => {
    const { container } = render(<StageStrip steps={STEPS} current={1} />)
    const text = container.textContent ?? ''
    // 三个阶段名都在
    for (const s of STEPS) expect(text).toContain(s)
    container.remove()
  })

  it('failedAt 命中时该阶段标失败态', () => {
    const { container } = render(<StageStrip steps={STEPS} current={2} failedAt={2} />)
    expect(container.textContent).toContain('匹配')
    container.remove()
  })

  it('不传 failedAt 时不会渲染失败图标语义', () => {
    const { container } = render(<StageStrip steps={STEPS} current={0} />)
    expect(container.querySelectorAll('svg').length).toBeGreaterThan(0)
    container.remove()
  })
})

describe('StageSteps（垂直步进器）', () => {
  it('进行中阶段显示「进行中…」', () => {
    const { container } = render(<StageSteps steps={STEPS} current={1} />)
    expect(within(container).getByText('进行中…')).toBeTruthy()
    container.remove()
  })

  it('失败阶段显示「失败」且不再显示进行中', () => {
    const { container } = render(<StageSteps steps={STEPS} current={1} failedAt={1} />)
    expect(within(container).getByText('失败')).toBeTruthy()
    expect(within(container).queryByText('进行中…')).toBeNull()
    container.remove()
  })

  it('全部步骤渲染为列表项', () => {
    const { container } = render(<StageSteps steps={STEPS} current={0} />)
    expect(container.querySelectorAll('li')).toHaveLength(STEPS.length)
    container.remove()
  })
})

describe('HistoryParts', () => {
  it('HistoryButton 点击回调', () => {
    const onClick = vi.fn()
    const { container } = render(<HistoryButton title="历史记录" onClick={onClick} />)
    fireEvent.click(within(container).getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
    container.remove()
  })

  it('HistoryPager：首页禁用「上一页」，末页禁用「下一页」', () => {
    const onChange = vi.fn()
    const { container } = render(<HistoryPager page={1} totalPages={3} onChange={onChange} />)
    const prev = within(container).getByRole('button', { name: /上一页/ }) as HTMLButtonElement
    const next = within(container).getByRole('button', { name: /下一页/ }) as HTMLButtonElement
    expect(prev.disabled).toBe(true)
    expect(next.disabled).toBe(false)
    expect(within(container).getByText('第 1 / 3 页')).toBeTruthy()
    container.remove()
  })

  it('HistoryPager：翻页回调夹在合法范围', () => {
    const onChange = vi.fn()
    const { container } = render(<HistoryPager page={2} totalPages={3} onChange={onChange} />)
    fireEvent.click(within(container).getByRole('button', { name: /上一页/ }))
    expect(onChange).toHaveBeenCalledWith(1)
    fireEvent.click(within(container).getByRole('button', { name: /下一页/ }))
    expect(onChange).toHaveBeenCalledWith(3)
    container.remove()
  })

  it('HistoryPager：末页时下一页禁用', () => {
    const { container } = render(<HistoryPager page={3} totalPages={3} onChange={vi.fn()} />)
    expect((within(container).getByRole('button', { name: /下一页/ }) as HTMLButtonElement).disabled).toBe(true)
    container.remove()
  })

  it('HistoryHeader 显示标题、条数与右侧插槽', () => {
    const { container } = render(
      <HistoryHeader title="解析历史" count={12}>
        <span>筛选</span>
      </HistoryHeader>,
    )
    expect(within(container).getByText('解析历史')).toBeTruthy()
    expect(within(container).getByText('12 条')).toBeTruthy()
    expect(within(container).getByText('筛选')).toBeTruthy()
    container.remove()
  })
})

describe('HistoryError', () => {
  it('显示错误文案与重试按钮', () => {
    const onRetry = vi.fn()
    const { container } = render(<HistoryError error="加载失败" onRetry={onRetry} />)
    expect(within(container).getByText(/加载失败/)).toBeTruthy()
    fireEvent.click(within(container).getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
    container.remove()
  })
})

describe('shared', () => {
  it('Spinner 渲染 svg 且对读屏隐藏', () => {
    const { container } = render(<Spinner />)
    const svg = container.querySelector('svg')!
    expect(svg.getAttribute('aria-hidden')).toBe('true')
    container.remove()
  })

  it('ToolShell：无 onDropFiles 时不注册拖放（不显示高亮层）', () => {
    const { container } = render(
      <ToolShell icon={<i />} title="工具" endpoint="/api/x">
        <span>内容</span>
      </ToolShell>,
    )
    expect(within(container).getByText('工具')).toBeTruthy()
    expect(container.textContent).not.toContain('松开以选择文件')
    container.remove()
  })

  it('ToolShell：拖入匹配后缀的文件时回调收到文件', () => {
    const onDropFiles = vi.fn()
    const { container } = render(
      <ToolShell icon={<i />} title="工具" endpoint="/api/x" dropAccept=".doc,.docx" onDropFiles={onDropFiles}>
        <span>内容</span>
      </ToolShell>,
    )
    const card = container.firstElementChild as HTMLElement
    const file = new File(['x'], '起诉状.DOCX', { type: '' })
    fireEvent.drop(card, { dataTransfer: { files: [file] } })
    expect(onDropFiles).toHaveBeenCalledWith([file])
    container.remove()
  })

  it('ToolShell：全部后缀不匹配时提示且不回调', () => {
    const onDropFiles = vi.fn()
    const { container } = render(
      <ToolShell icon={<i />} title="工具" endpoint="/api/x" dropAccept=".doc" onDropFiles={onDropFiles}>
        <span>内容</span>
      </ToolShell>,
    )
    const card = container.firstElementChild as HTMLElement
    fireEvent.drop(card, { dataTransfer: { files: [new File(['x'], 'a.txt')] } })
    expect(onDropFiles).not.toHaveBeenCalled()
    expect(toast.warning).toHaveBeenCalled()
    container.remove()
  })

  it('ToolShell：无文件拖入时不触发任何回调', () => {
    const onDropFiles = vi.fn()
    const { container } = render(
      <ToolShell icon={<i />} title="工具" endpoint="/api/x" dropAccept=".doc" onDropFiles={onDropFiles}>
        <span>内容</span>
      </ToolShell>,
    )
    const card = container.firstElementChild as HTMLElement
    fireEvent.drop(card, { dataTransfer: { files: [] } })
    expect(onDropFiles).not.toHaveBeenCalled()
    container.remove()
  })

  it('FilePicker：选择文件后回调文件数组', () => {
    const onPick = vi.fn()
    const { container } = render(
      <FilePicker label="选择文件" hint="支持 doc" accept=".doc" onPick={onPick} />,
    )
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'], 'a.doc')
    fireEvent.change(input, { target: { files: [file] } })
    expect(onPick).toHaveBeenCalledWith([file])
    container.remove()
  })

  it('FilePicker：disabled 时输入框禁用', () => {
    const { container } = render(
      <FilePicker label="选择" hint="h" accept=".doc" disabled onPick={vi.fn()} />,
    )
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.disabled).toBe(true)
    container.remove()
  })
})
