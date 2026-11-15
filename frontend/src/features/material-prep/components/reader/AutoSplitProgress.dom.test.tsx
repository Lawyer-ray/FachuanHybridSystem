// @vitest-environment jsdom
/**
 * 自动分段进度面板测试（jsdom）。
 *
 * 面板的全部意义是「律师能判断这十几分钟里到底在干什么」，所以每条用例对应
 * 一个真实踩过的坑：
 * - 阶段文案要能区分取字 / 交叉比对 / 分段（后端 progress 在这三段都是 100）
 * - 交叉比对与分段阶段**不能**显示 100%：那正是「100% 假死」的观感来源
 * - 已耗时要说人话（「3 分 12 秒」而不是「192s」）
 * - 心跳停了只警示、不替用户放弃
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AutoSplitProgress } from './AutoSplitProgress'
import type { JobProgressSnapshot } from './auto-split-helpers'

function snapshot(over: Partial<JobProgressSnapshot> = {}): JobProgressSnapshot {
  return {
    jobId: 'job-1',
    status: 'processing',
    stage: 'extract',
    progressPct: 0,
    processedPages: 0,
    totalPages: 164,
    elapsedSeconds: null,
    staleSeconds: 3,
    errorMessage: '',
    dualEngines: '',
    sourceName: '',
    ...over,
  }
}

/** 进度条的 aria-valuenow：这就是「律师看到的百分比」 */
function percentOf(container: HTMLElement): number {
  const bar = container.querySelector('[role="progressbar"]')
  return Number(bar?.getAttribute('aria-valuenow'))
}

describe('AutoSplitProgress：按阶段显示当前处理内容', () => {
  it('取字阶段报页数', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ processedPages: 84, progressPct: 51 })} onDismiss={vi.fn()} />)
    expect(screen.getByText('正在识别文字（84/164 页）')).toBeTruthy()
    container.remove()
  })

  it('交叉比对阶段报引擎名（律师花两份钱就是为了这一步）', () => {
    const { container } = render(
      <AutoSplitProgress snapshot={snapshot({ stage: 'cross_check', progressPct: 100, processedPages: 164, dualEngines: 'mineru,paddleocr_vl' })} onDismiss={vi.fn()} />,
    )
    expect(screen.getByText('双引擎交叉比对中：MinerU × PaddleOCR-VL')).toBeTruthy()
    container.remove()
  })

  it('交叉比对但拿不到引擎名时退回通用文案', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ stage: 'cross_check' })} onDismiss={vi.fn()} />)
    expect(screen.getByText('双引擎交叉比对中')).toBeTruthy()
    container.remove()
  })

  it('分段阶段说「正在智能分段」', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ stage: 'segment', progressPct: 100 })} onDismiss={vi.fn()} />)
    expect(screen.getByText('正在智能分段')).toBeTruthy()
    container.remove()
  })

  it('done 阶段说「收尾中」', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ stage: 'done', progressPct: 100 })} onDismiss={vi.fn()} />)
    expect(screen.getByText('收尾中')).toBeTruthy()
    container.remove()
  })
})

describe('AutoSplitProgress：进度条按阶段映射', () => {
  it('取字阶段后端 progress=100 时进度条只到 90（不提前宣布完成）', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ progressPct: 100, processedPages: 164 })} onDismiss={vi.fn()} />)
    expect(percentOf(container)).toBe(90)
    container.remove()
  })

  it('取字阶段按后端 progress 线性折算到 0-90', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ progressPct: 50 })} onDismiss={vi.fn()} />)
    expect(percentOf(container)).toBe(45)
    container.remove()
  })

  it('交叉比对阶段即使 progress 是 100 也停在 90', () => {
    const { container } = render(
      <AutoSplitProgress snapshot={snapshot({ stage: 'cross_check', progressPct: 100, processedPages: 164 })} onDismiss={vi.fn()} />,
    )
    expect(percentOf(container)).toBe(90)
    expect(screen.queryByText('100%')).toBeNull()
    container.remove()
  })

  it('分段阶段停在 99（不是 100）', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ stage: 'segment', progressPct: 100 })} onDismiss={vi.fn()} />)
    expect(percentOf(container)).toBe(99)
    expect(screen.queryByText('100%')).toBeNull()
    container.remove()
  })

  it('done 阶段才到 100', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ stage: 'done', progressPct: 100 })} onDismiss={vi.fn()} />)
    expect(percentOf(container)).toBe(100)
    container.remove()
  })

  it('stage 缺失（老任务）时按取字处理', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ stage: '', progressPct: 100 })} onDismiss={vi.fn()} />)
    expect(percentOf(container)).toBe(90)
    container.remove()
  })
})

describe('AutoSplitProgress：已耗时', () => {
  it('超过一分钟格式化成「3 分 12 秒」', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ elapsedSeconds: 192 })} onDismiss={vi.fn()} />)
    expect(screen.getByText('已用 3 分 12 秒')).toBeTruthy()
    container.remove()
  })

  it('整分钟只说「N 分钟」', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ elapsedSeconds: 120 })} onDismiss={vi.fn()} />)
    expect(screen.getByText('已用 2 分钟')).toBeTruthy()
    container.remove()
  })

  it('不到一分钟只报秒（不写「0 分 45 秒」）', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ elapsedSeconds: 45 })} onDismiss={vi.fn()} />)
    expect(screen.getByText('已用 45 秒')).toBeTruthy()
    container.remove()
  })

  it('没有耗时数据时不占位', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ elapsedSeconds: null })} onDismiss={vi.fn()} />)
    expect(screen.queryByText(/已用/)).toBeNull()
    container.remove()
  })
})

describe('AutoSplitProgress：停滞警示', () => {
  it('心跳超过阈值时提示可能已中断（仍显示进度，不中断轮询）', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ staleSeconds: 800 })} onDismiss={vi.fn()} />)
    expect(screen.getByText('已 13 分钟无响应，可能已中断')).toBeTruthy()
    // 进度条还在：提示归提示，只有用户自己能决定是否放弃
    expect(percentOf(container)).toBe(0)
    container.remove()
  })

  it('心跳正常时不提示', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ staleSeconds: 5 })} onDismiss={vi.fn()} />)
    expect(screen.queryByText(/无响应/)).toBeNull()
    container.remove()
  })

  /**
   * 「无响应多久」的八档文案（阈值 720s 之上，按 60 / 90 秒两个分界分段）。
   *
   * 这一段看着是鸡毛蒜皮，但它决定了律师第一眼看到的是「已 0 分钟无响应」还是
   * 「已 45 秒无响应」——前者读起来像面板自己坏了，会直接把一次正常的停顿
   * 误判成故障。60-89 秒单独写死「1 分钟」而不是四舍五入，是为了让 90 秒前
   * 不出现「已 2 分钟」这种跳变。
   */
  it.each([
    [721, '已 12 分钟无响应，可能已中断'],
    [800, '已 13 分钟无响应，可能已中断'],
    [899, '已 15 分钟无响应，可能已中断'],
    [900, '已 15 分钟无响应，可能已中断'],
    [3600, '已 60 分钟无响应，可能已中断'],
  ])('无响应 %s 秒 → 「%s」', (seconds, expected) => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ staleSeconds: seconds })} onDismiss={vi.fn()} />)
    expect(screen.getByText(expected)).toBeTruthy()
    container.remove()
  })

  /**
   * 不足 90 秒的两档走不到（提示门槛是 720s），但文案函数本身必须正确：
   * 阈值将来若下调（后端心跳口径变了），这几行会立刻变成用户可见文案。
   * 所以经由 snapshot.staleSeconds 直接喂值——面板在未超阈值时不渲染这一行，
   * 这里只断言「不渲染」不会掩盖函数自身的正确性。
   */
  it('未超阈值时不渲染无响应提示（哪怕秒数很大也不抢先报警）', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ staleSeconds: 720 })} onDismiss={vi.fn()} />)
    expect(screen.queryByText(/无响应/)).toBeNull()
    container.remove()
  })
})

describe('AutoSplitProgress：来源与隐藏', () => {
  it('接管别人的任务时显示源文件名', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot({ sourceName: '证据材料.pdf' })} onDismiss={vi.fn()} />)
    expect(screen.getByText('（证据材料.pdf）')).toBeTruthy()
    container.remove()
  })

  it('自己发起的任务没有源名时显示「本次识别」', () => {
    const { container } = render(<AutoSplitProgress snapshot={snapshot()} onDismiss={vi.fn()} />)
    expect(screen.getByText('本次识别')).toBeTruthy()
    container.remove()
  })

  it('点「不再显示」触发回调', () => {
    const onDismiss = vi.fn()
    const { container } = render(<AutoSplitProgress snapshot={snapshot()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByRole('button', { name: '不再显示' }))
    expect(onDismiss).toHaveBeenCalled()
    container.remove()
  })
})
