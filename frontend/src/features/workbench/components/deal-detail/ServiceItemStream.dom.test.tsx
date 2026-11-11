// @vitest-environment jsdom
/**
 * ServiceItemStream：服务事项流（非诉·常法顾问的左栏主角）。
 *
 * 契约要点：
 * - 空态分三种：读取中 / 已有事项源但目录为空 / 根本认不出「办案」目录
 * - 事项行展开是**懒加载**：只有「有 loadFiles + 有 subpath + fileCount>0」才可展开，
 *   每次展开只取一次（再展开用缓存），取失败按「没有文件」处理而不是把错误嗓门放大
 * - 交付物点击走 onOpenDeliverable，且不能冒泡触发整行折叠
 * - 事项源选择器的空值代表「自动识别」
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ServiceItemStream, type ServiceItem } from './ServiceItemStream'

function item(over: Partial<ServiceItem> = {}): ServiceItem {
  return { date: '2026-04-27', kind: '合同', title: '草拟付款确认书', status: 'done', ...over }
}

const FILES = [
  { name: '付款确认书-v1.docx', subpath: '3-办案/a/v1.docx', size: 1024 },
  { name: '付款确认书-v2.docx', subpath: '3-办案/a/v2.docx', size: 2048 },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ServiceItemStream · 表头与空态', () => {
  it('标题旁的小圆点显示事项条数', () => {
    render(<ServiceItemStream items={[item(), item({ title: '租赁合同审查' })]} />)
    expect(screen.getByText('服务事项')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
  })

  it('读取中：空态文案说明正在读目录', () => {
    render(<ServiceItemStream items={[]} isLoading />)
    expect(screen.getByText('正在读取事项目录…')).toBeTruthy()
  })

  it('已有事项源目录但里面没事项：告诉律师怎么建目录', () => {
    render(<ServiceItemStream items={[]} sourceSubpath="3-办案" />)
    expect(screen.getByText('该目录下还没有事项。按「日期-事项」建子文件夹，这里就会自动列出来。')).toBeTruthy()
  })

  it('认不出「办案」目录：提示用下拉指定或新建', () => {
    render(<ServiceItemStream items={[]} />)
    expect(screen.getByText(/没有找到「办案」目录/)).toBeTruthy()
  })

  it('没有事项时不渲染表头（空表头比空态更噪）', () => {
    render(<ServiceItemStream items={[]} />)
    expect(screen.queryByRole('table')).toBeNull()
  })
})

describe('ServiceItemStream · 事项源选择器', () => {
  const CANDIDATES = [
    { name: '3-办案', subpath: '3-办案' },
    { name: '4-日常咨询', subpath: '4-日常咨询' },
  ]

  it('自动识别项为空值，选中候选回传其 subpath', () => {
    const onChangeSource = vi.fn()
    render(
      <ServiceItemStream items={[]} candidates={CANDIDATES} sourceSubpath="3-办案" onChangeSource={onChangeSource} />,
    )
    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.value).toBe('3-办案')
    expect(screen.getByRole('option', { name: '自动（找「办案」目录）' })).toBeTruthy()

    fireEvent.change(select, { target: { value: '4-日常咨询' } })
    expect(onChangeSource).toHaveBeenCalledWith('4-日常咨询')
  })

  it('切回自动识别时回传 null（不是空串）', () => {
    const onChangeSource = vi.fn()
    render(<ServiceItemStream items={[]} candidates={CANDIDATES} onChangeSource={onChangeSource} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } })
    expect(onChangeSource).toHaveBeenCalledWith(null)
  })

  it('没有候选目录时不渲染选择器', () => {
    render(<ServiceItemStream items={[]} onChangeSource={vi.fn()} />)
    expect(screen.queryByRole('combobox')).toBeNull()
  })
})

describe('ServiceItemStream · 事项行', () => {
  it('日期、类型、事项、状态逐列照实显示', () => {
    render(<ServiceItemStream items={[item({ detail: '客户：某某银行' })]} />)
    expect(screen.getByText('2026-04-27')).toBeTruthy()
    expect(screen.getByText('合同')).toBeTruthy()
    expect(screen.getByText('草拟付款确认书')).toBeTruthy()
    expect(screen.getByText('客户：某某银行')).toBeTruthy()
    expect(screen.getByText('已交付')).toBeTruthy()
  })

  it('三种状态各用一句中文（进行中加粗 / 待办淡化）', () => {
    render(
      <ServiceItemStream
        items={[
          item({ date: '2026-01-01', status: 'done' }),
          item({ date: '2026-01-02', status: 'doing' }),
          item({ date: '2026-01-03', status: 'todo' }),
        ]}
      />,
    )
    expect(screen.getByText('已交付')).toBeTruthy()
    expect(screen.getByText('进行中')).toBeTruthy()
    expect(screen.getByText('待办')).toBeTruthy()
  })

  it('日期为空写破折号；today 高亮额外给一行「今天」', () => {
    const { container } = render(
      <ServiceItemStream
        items={[item({ date: '', today: true }), item({ date: '2026-02-02', today: true })]}
      />,
    )
    // 第一行日期格：破折号 + 「今天」副行
    const cells = container.querySelectorAll('tbody td:first-child')
    expect(cells[0]!.textContent).toBe('—今天')
    expect(cells[1]!.textContent).toBe('2026-02-02今天')
  })

  it('没有事项名时显示「未命名事项」占位', () => {
    render(<ServiceItemStream items={[item({ title: '' })]} />)
    expect(screen.getByText('未命名事项')).toBeTruthy()
  })

  it('有文件数就写「N 个文件」，没有就写破折号', () => {
    render(
      <ServiceItemStream
        items={[item({ date: '2026-01-01', fileCount: 3 }), item({ date: '2026-01-02' })]}
      />,
    )
    expect(screen.getByText('3 个文件')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
  })
})

describe('ServiceItemStream · 交付物懒加载', () => {
  it('没给 loadFiles 的事项行不可展开：点了也不发请求', () => {
    const loadFiles = vi.fn()
    const row = item({ subpath: '3-办案/a', fileCount: 2 })
    render(<ServiceItemStream items={[row]} />)
    fireEvent.click(screen.getByText(row.title))
    // 不传 loadFiles → expandable=false → 不发请求、不出现交付物行
    expect(loadFiles).not.toHaveBeenCalled()
    expect(screen.queryByText('读取交付物…')).toBeNull()
  })

  it('有 subpath 与 fileCount 才展开；展开取一次后收起/再展开复用缓存', async () => {
    const loadFiles = vi.fn().mockResolvedValue(FILES)
    const row = item({ subpath: '3-办案/a', fileCount: 2 })
    render(<ServiceItemStream items={[row]} loadFiles={loadFiles} />)

    fireEvent.click(screen.getByText(row.title))
    expect(await screen.findByText('付款确认书-v1.docx')).toBeTruthy()
    expect(loadFiles).toHaveBeenCalledTimes(1)
    expect(loadFiles).toHaveBeenCalledWith('3-办案/a')

    // 收起 → 交付物消失
    fireEvent.click(screen.getByText(row.title))
    expect(screen.queryByText('付款确认书-v1.docx')).toBeNull()

    // 再展开：不重复请求
    fireEvent.click(screen.getByText(row.title))
    expect(await screen.findByText('付款确认书-v2.docx')).toBeTruthy()
    expect(loadFiles).toHaveBeenCalledTimes(1)
  })

  it('fileCount 为 0 或未统计时不展开（避免空转一次目录扫描）', () => {
    const loadFiles = vi.fn().mockResolvedValue(FILES)
    const row = item({ subpath: '3-办案/a' })
    render(<ServiceItemStream items={[row]} loadFiles={loadFiles} />)
    fireEvent.click(screen.getByText(row.title))
    expect(loadFiles).not.toHaveBeenCalled()
  })

  it('取交付物失败按「没有文件」呈现，不弹错', async () => {
    const loadFiles = vi.fn().mockRejectedValue(new Error('目录不存在'))
    const row = item({ subpath: '3-办案/a', fileCount: 1 })
    render(<ServiceItemStream items={[row]} loadFiles={loadFiles} />)
    fireEvent.click(screen.getByText(row.title))
    expect(await screen.findByText('该事项下没有文件（只有子目录或为空）')).toBeTruthy()
  })

  it('返回空数组同样走「没有文件」文案', async () => {
    const loadFiles = vi.fn().mockResolvedValue([])
    const row = item({ subpath: '3-办案/a', fileCount: 1 })
    render(<ServiceItemStream items={[row]} loadFiles={loadFiles} />)
    fireEvent.click(screen.getByText(row.title))
    expect(await screen.findByText('该事项下没有文件（只有子目录或为空）')).toBeTruthy()
  })

  it('点交付物把 { subpath, name } 交给调用方，且不折叠整行', async () => {
    const loadFiles = vi.fn().mockResolvedValue(FILES)
    const onOpenDeliverable = vi.fn()
    const row = item({ subpath: '3-办案/a', fileCount: 2 })
    render(<ServiceItemStream items={[row]} loadFiles={loadFiles} onOpenDeliverable={onOpenDeliverable} />)

    fireEvent.click(screen.getByText(row.title))
    const fileBtn = await screen.findByText('付款确认书-v2.docx')
    fireEvent.click(fileBtn)

    expect(onOpenDeliverable).toHaveBeenCalledWith({
      subpath: '3-办案/a/v2.docx',
      name: '付款确认书-v2.docx',
    })
    // stopPropagation 生效：整行没有收起，另一份交付物还在
    await waitFor(() => expect(screen.getByText('付款确认书-v1.docx')).toBeTruthy())
  })
})

describe('ServiceItemStream · 页脚', () => {
  it('「记事项」按钮把动作交回调用方', () => {
    const onAdd = vi.fn()
    render(<ServiceItemStream items={[item()]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /记事项/ }))
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('note 作为表尾说明显示', () => {
    render(<ServiceItemStream items={[item()]} note="本服务期 2026-01-01 至 2026-12-31 内的事项" />)
    expect(screen.getByText('本服务期 2026-01-01 至 2026-12-31 内的事项')).toBeTruthy()
  })
})
