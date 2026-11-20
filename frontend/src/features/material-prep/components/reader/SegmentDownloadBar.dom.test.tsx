// @vitest-environment jsdom
/**
 * 「已转好产物」下载 UI 的 DOM 测试（jsdom）。
 *
 * 每个用例都对着一条会真出事的规矩，不是凑覆盖率：
 *
 * 1. **下载必须经一次性票据**。本仓库有过明确事故：附件下载用裸 `<a href>` 打开
 *    后端端点，浏览器带不上 localStorage 里的 JWT、后端又刻意不收 `?token=`，
 *    于是任何账号下载都是 401（回归注释见 `inbox/components/InboxView.dom.test.tsx`）。
 *    所以这里断言的是「换票函数收到的路径」，而且换票用的是**真实的 appendTicket**
 *    ——打桩成固定 `?ticket=` 的假实现，就把「带 query 的 URL 拼成两个 `?`」
 *    这个坑一起测没了（`/download?ids=12,15` 必须变成 `&ticket=`）。
 * 2. **空选中不渲染「下载选中（0）」**：点下去后端会退回整包，等于悄悄改用户意图。
 * 3. **半选态**只能靠 DOM 的 `indeterminate`，受控 checked 会把它冲掉。
 * 4. **下载中不许重复取票**：票据一次性 + 只活 60 秒，连点两次白换一张，
 *    后一次拿到的是已作废的票据（表现就是「下载功能坏了」）。
 * 5. **没有后端产物时整块不渲染**：一排永远点不动的灰按钮比没有更糟。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const dlMock = vi.hoisted(() => ({
  withDownloadTicket: vi.fn(),
  downloadUrl: vi.fn(),
}))

// 只替换「发请求换票」这一步，appendTicket 用真货——见文件头第 1 条
vi.mock('@/lib/download-ticket', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/download-ticket')>()
  return {
    appendTicket: actual.appendTicket,
    stripTicket: actual.stripTicket,
    withDownloadTicket: dlMock.withDownloadTicket,
  }
})
vi.mock('@/lib/download', () => ({ downloadUrl: dlMock.downloadUrl, saveBlob: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

// Radix 右键菜单在 jsdom 里既不参与本次断言、又会带出一条 legacy build 告警，
// 与 Rail.dom.test 同样打桩。
vi.mock('@/components/ui/context-menu', () => ({
  ContextMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuItem: ({
    children,
    onSelect,
    disabled,
  }: {
    children: React.ReactNode
    onSelect?: () => void
    disabled?: boolean
  }) => (
    <button type="button" disabled={disabled} onClick={() => onSelect?.()}>
      {children}
    </button>
  ),
  ContextMenuSeparator: () => <hr />,
}))

// 落点接线测试只看 Rail 传给每一行的 `download`（行内的视觉细节由 Harness 那几组覆盖），
// 所以把行本身打桩成只记录的探针——与 Rail.dom.test 同一手法。
const railRows = vi.hoisted(() => [] as Array<Record<string, unknown>>)
vi.mock('./RailSegRow', () => ({
  RailSegRow: (p: { si: number; download?: unknown }) => {
    railRows.push(p as unknown as Record<string, unknown>)
    return <div data-testid={`row-${String(p.si)}`} />
  },
}))

import { appendTicket } from '@/lib/download-ticket'
import { toast } from 'sonner'
import { Rail } from './Rail'
import { SegmentDownloadBar, SegmentDownloadMenuItems, SegmentSelectBox } from './SegmentDownloadBar'
import { useSegmentDownloads, type DownloadableSegment, type SegmentRowDownload } from './use-segment-selection'

/**
 * 与 Rail 的组合方式一致：工具条一份状态，每个段行取自己的 `rowFor(pk)`。
 * 这里不渲染整个 Rail（那要 20 多个与下载无关的 props），但用到的三个组件与
 * hook 都是产线代码，没有为测试另写一份「假行」。
 */
function Harness({ segments }: { segments: DownloadableSegment[] }) {
  const dl = useSegmentDownloads(segments)
  return (
    <div>
      <SegmentDownloadBar dl={dl} />
      {segments.map((seg) => {
        const row = dl.rowFor(seg.pk)
        return (
          <div key={seg.pk} data-row>
            <SegmentSelectBox row={row} name={seg.name} />
            <span>{seg.name}</span>
            <SegmentDownloadMenuItems row={row} />
          </div>
        )
      })}
    </div>
  )
}

/** 三段两任务：真实包可以有多份 PDF，各自由不同识别任务产出（zip 与 ids 都是按任务的） */
const SEGMENTS: DownloadableSegment[] = [
  { pk: 11, jobId: 'job-1', name: '起诉状' },
  { pk: 12, jobId: 'job-1', name: '证据清单' },
  { pk: 15, jobId: 'job-2', name: '借款合同' },
]

const pdfBtn = (i = 0) => screen.getAllByRole('button', { name: '下载 PDF' })[i] as HTMLButtonElement
const mdBtn = (i = 0) => screen.getAllByRole('button', { name: '下载 Markdown' })[i] as HTMLButtonElement
const boxOf = (name: string) => screen.getByRole('checkbox', { name }) as HTMLInputElement
const selectAll = () => boxOf('全选')

beforeEach(() => {
  vi.clearAllMocks()
  railRows.length = 0
  // 换票成功路径：真实 appendTicket 拼 ?ticket= / &ticket=
  dlMock.withDownloadTicket.mockImplementation(async (path: string) => appendTicket(path, 'TICKET123'))
})

describe('SegmentDownloadBar：没有产物就整块不渲染', () => {
  it('segments 为空（还没分段 / 人工拆的段 / 旧草稿）→ 工具条与行内控件都不出现', () => {
    const { container } = render(<Harness segments={[]} />)
    expect(container.querySelector('[data-segment-download-bar]')).toBeNull()
    expect(screen.queryByRole('button', { name: '整包下载' })).toBeNull()
    expect(screen.queryByRole('checkbox')).toBeNull()
    container.remove()
  })

  it('有产物时才出现工具条与每行的下载项', () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    expect(container.querySelector('[data-segment-download-bar]')).toBeTruthy()
    expect(screen.getByRole('button', { name: '整包下载' })).toBeTruthy()
    expect(screen.getAllByRole('button', { name: '下载 PDF' })).toHaveLength(3)
    expect(screen.getAllByRole('button', { name: '下载 Markdown' })).toHaveLength(3)
    container.remove()
  })
})

describe('多选：全选 / 半选 / 空选中不出现批量按钮', () => {
  it('一段都没勾时「下载选中」不存在（不是渲染成禁用态）', () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    expect(screen.queryByRole('button', { name: /下载选中/ })).toBeNull()
    expect(selectAll().checked).toBe(false)
    expect(selectAll().indeterminate).toBe(false)
    container.remove()
  })

  it('全选 → 三段都勾上、按钮显示「下载选中（3）」；再点一次取消全选', () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(selectAll())
    expect(boxOf('选择 起诉状').checked).toBe(true)
    expect(boxOf('选择 证据清单').checked).toBe(true)
    expect(boxOf('选择 借款合同').checked).toBe(true)
    expect(screen.getByRole('button', { name: '下载选中（3）' })).toBeTruthy()

    fireEvent.click(selectAll())
    expect(boxOf('选择 起诉状').checked).toBe(false)
    expect(screen.queryByRole('button', { name: /下载选中/ })).toBeNull()
    container.remove()
  })

  it('勾了一部分 → 全选框半选（indeterminate），勾满后转为全选', () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(boxOf('选择 证据清单'))
    // 受控 checked 会把 indeterminate 冲掉，全靠 render 时补写；这条就是那个点的锁
    expect(selectAll().indeterminate).toBe(true)
    expect(selectAll().checked).toBe(false)

    fireEvent.click(selectAll()) // 半选态点一下 = 选满（不是清空）
    expect(boxOf('选择 起诉状').checked).toBe(true)
    expect(selectAll().indeterminate).toBe(false)
    expect(selectAll().checked).toBe(true)
    container.remove()
  })
})

describe('单个下载（右键菜单项）：PDF / MD 各一次，且都带票据', () => {
  it('点「下载 PDF」：换票入参是单段 pdf 端点，下载用的是带 ticket 的地址', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(pdfBtn(0))

    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalled())
    expect(dlMock.withDownloadTicket).toHaveBeenCalledTimes(1)
    expect(dlMock.withDownloadTicket).toHaveBeenCalledWith('/api/v1/pdf-splitting/jobs/job-1/segments/11/pdf')
    expect(dlMock.downloadUrl).toHaveBeenCalledWith(
      '/api/v1/pdf-splitting/jobs/job-1/segments/11/pdf?ticket=TICKET123',
    )
    container.remove()
  })

  it('点「下载 Markdown」：同一段、只有末段换成 md', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(mdBtn(1))

    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalled())
    expect(dlMock.withDownloadTicket).toHaveBeenCalledWith('/api/v1/pdf-splitting/jobs/job-1/segments/12/md')
    container.remove()
  })

  it('第二份 PDF 的段走自己的任务号（多源包不能被拼成同一个 job）', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(pdfBtn(2))

    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalled())
    expect(dlMock.withDownloadTicket).toHaveBeenCalledWith('/api/v1/pdf-splitting/jobs/job-2/segments/15/pdf')
    container.remove()
  })
})

describe('批量下载：ids 是段主键，票据拼在 query 后面用 &', () => {
  it('选中同一任务的两段 → /download?ids=11,12 → &ticket=（不是第二个 ?）', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(boxOf('选择 起诉状'))
    fireEvent.click(boxOf('选择 证据清单'))
    fireEvent.click(screen.getByRole('button', { name: '下载选中（2）' }))

    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalled())
    expect(dlMock.withDownloadTicket).toHaveBeenCalledWith('/api/v1/pdf-splitting/jobs/job-1/download?ids=11,12')
    // 这就是本次最容易错的一行：带 query 的 URL 必须拼 &ticket=
    expect(dlMock.downloadUrl).toHaveBeenCalledWith(
      '/api/v1/pdf-splitting/jobs/job-1/download?ids=11,12&ticket=TICKET123',
    )
    container.remove()
  })

  it('选中跨任务的两段 → 按任务各下一次（一个请求装不下两个 job）', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(boxOf('选择 起诉状'))
    fireEvent.click(boxOf('选择 借款合同'))
    fireEvent.click(screen.getByRole('button', { name: '下载选中（2）' }))

    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalledTimes(2))
    expect(dlMock.withDownloadTicket.mock.calls.map((c) => c[0])).toEqual([
      '/api/v1/pdf-splitting/jobs/job-1/download?ids=11',
      '/api/v1/pdf-splitting/jobs/job-2/download?ids=15',
    ])
    container.remove()
  })

  it('整包下载不带 ids（后端按整个任务打包）', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(screen.getByRole('button', { name: '整包下载' }))

    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalledTimes(2))
    expect(dlMock.withDownloadTicket.mock.calls.map((c) => c[0])).toEqual([
      '/api/v1/pdf-splitting/jobs/job-1/download',
      '/api/v1/pdf-splitting/jobs/job-2/download',
    ])
    container.remove()
  })
})

describe('下载中：置忙 + 不重复取票', () => {
  it('连点两次同一个文件的 PDF 只换一次票；完成后按钮恢复可点', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    let release: (url: string) => void = () => {}
    dlMock.withDownloadTicket.mockImplementationOnce(
      () =>
        new Promise<string>((resolve) => {
          release = resolve
        }),
    )

    const btn = pdfBtn(0)
    // 两下点击必须在同一个 act 批次里：分开各自 flush 一次，第二次会被 disabled 挡住，
    // 那就测不到「setState 还没落到 DOM 时靠 ref 同步闸门挡住第二次」这条
    act(() => {
      fireEvent.click(btn)
      fireEvent.click(btn)
    })
    expect(dlMock.withDownloadTicket).toHaveBeenCalledTimes(1)

    release('/api/v1/pdf-splitting/jobs/job-1/segments/11/pdf?ticket=TICKET123')
    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(pdfBtn(0).disabled).toBe(false))
    container.remove()
  })

  it('下载中其它按钮一起禁用（同一时刻只允许一个换票请求在飞）', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    let release: (url: string) => void = () => {}
    dlMock.withDownloadTicket.mockImplementationOnce(
      () =>
        new Promise<string>((resolve) => {
          release = resolve
        }),
    )
    fireEvent.click(pdfBtn(0))

    expect(mdBtn(0).disabled).toBe(true)
    expect(pdfBtn(1).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '整包下载' }) as HTMLButtonElement).disabled).toBe(true)

    release('/api/v1/pdf-splitting/jobs/job-1/segments/11/pdf?ticket=TICKET123')
    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalledTimes(1))
    container.remove()
  })

  /**
   * 失败路径。注意 `withDownloadTicket` 的真实语义：换票失败**不抛**，原样返回入参
   * （lib/download-ticket 的设计），所以这里按原样返回打桩——比 mock 一个 rejection
   * 更接近线上。断言两件事：报一句人话的 toast，且**绝不打开裸链接**（那只会是
   * 一个写着 401/403 的新标签页，正是 M-2 事故的观感）；同时选择必须留着，
   * 否则律师得把几十段重新勾一遍。
   */
  it('换票失败（原样返回 URL）→ toast 报错、不开裸链接、选中不丢', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(boxOf('选择 起诉状'))
    dlMock.withDownloadTicket.mockImplementationOnce(async (path: string) => path)

    fireEvent.click(screen.getByRole('button', { name: /下载选中/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(dlMock.downloadUrl).not.toHaveBeenCalled()
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(expect.stringContaining('票据'))
    expect(boxOf('选择 起诉状').checked).toBe(true)
    expect(screen.getByRole('button', { name: '下载选中（1）' })).toBeTruthy()
    container.remove()
  })

  it('换票接口直接抛错也只挂这一次：toast 后置忙复位、选中仍在', async () => {
    const { container } = render(<Harness segments={SEGMENTS} />)
    fireEvent.click(boxOf('选择 起诉状'))
    dlMock.withDownloadTicket.mockRejectedValueOnce(new Error('503 Service Unavailable'))

    fireEvent.click(screen.getByRole('button', { name: /下载选中/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(dlMock.downloadUrl).not.toHaveBeenCalled()
    expect(boxOf('选择 起诉状').checked).toBe(true)
    // 置忙必须复位，否则这个包从此再也不能下载
    await waitFor(() =>
      expect((screen.getByRole('button', { name: '整包下载' }) as HTMLButtonElement).disabled).toBe(false),
    )
    container.remove()
  })
})

describe('Rail 落点：只有带后端出处的段才出下载控件', () => {
  const segWithRef = {
    id: 's1',
    t: '起诉状',
    fn: '起诉状',
    refs: [{ mi: 0, p: 1 }],
    manual: false,
    splitRef: { jobId: 'job-1', pk: 11 },
  }
  // 人工拆出来的段：后端没有它的产物，`splitRef` 缺省
  const manualSeg = { id: 's2', t: '', fn: '人工拆的', refs: [{ mi: 0, p: 2 }], manual: true }

  const renderRail = (segs: unknown[]) =>
    render(
      <Rail
        draft={{ mats: [{ partIndex: 0, n: '卷宗.pdf', k: 'pdf', pages: 2 }], segs, infos: [] } as never}
        onFocusSeg={vi.fn()}
        onRenameMat={vi.fn()}
        onRenameSeg={vi.fn()}
        onMergeSeg={vi.fn()}
        onMergeSegs={vi.fn()}
        onMoveSeg={vi.fn()}
      />,
    )

  it('工具条出现，且只有带 splitRef 的那一行拿到 download 视图模型', () => {
    const { container } = renderRail([segWithRef, manualSeg])
    expect(screen.getByRole('button', { name: '整包下载' })).toBeTruthy()
    const first = railRows[0]?.download as SegmentRowDownload | undefined
    expect(first?.checked).toBe(false)
    expect(railRows[1]?.download).toBeUndefined()
    container.remove()
  })

  it('整包都没有后端产物（全是人工拆的段）→ 工具条不渲染', () => {
    const { container } = renderRail([manualSeg])
    expect(container.querySelector('[data-segment-download-bar]')).toBeNull()
    container.remove()
  })
})
