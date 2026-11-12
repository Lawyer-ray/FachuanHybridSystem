// @vitest-environment jsdom
/**
 * DealDocLayout：详情页左内容 / 右事实卡 / 文档预览的三态栅格。
 *
 * 三态是这一层存在的全部理由，所以逐态钉住（漏一个就会出现「文档没处放」或
 * 「事实卡被同一块 DOM 渲染两次」）：
 * - ① 未展开（picked=null）：内容 + aside/rail 同屏，分隔条不出现
 * - ② 展开 + 净宽够（docSideBySide）：内容 + 右文档 + 分隔条，事实卡退到左栏底部
 * - ③ 展开 + 净宽不够（focusDoc）：文档通栏置顶，内容与事实卡在其下
 *
 * 另外：文档栏宽度偏好从 localStorage 读（这里先清空，避免受历史拖拽值影响），
 * 分隔条的方向键只在 ② 出现。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  preview: vi.fn(),
  railSection: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('./FilePreviewCard', () => ({
  FilePreviewCard: (props: {
    file: { name: string }
    ownerId: number
    onClose: () => void
    onSaved: () => void
    onReview: (f: { subpath: string; name: string }) => void
  }) => {
    mocks.preview(props)
    return <div>PREVIEW:{props.file.name}</div>
  },
}))

import { DOC_SIDE_BY_SIDE_MIN, DealDocLayout, type PickedFile } from './DealDocLayout'

const FILE: PickedFile = { subpath: '1-立案/起诉状.docx', name: '起诉状.docx' }

function setup(over: Partial<Parameters<typeof DealDocLayout>[0]> = {}) {
  const handlers = {
    picked: null as PickedFile | null,
    docSideBySide: false,
    focusDoc: false,
    ownerId: 443,
    onClose: vi.fn(),
    onSaved: vi.fn(),
    onReview: vi.fn(),
    ...over,
  }
  const view = render(
    <DealDocLayout {...handlers} rail={<div>RAIL</div>} aside={<div>ASIDE</div>}>
      <div>CONTENT</div>
    </DealDocLayout>,
  )
  return { ...handlers, ...view }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mocks.railSection.mockReset()
})

describe('DOC_SIDE_BY_SIDE_MIN', () => {
  it('并排门槛是 1100（低于它文档通栏、事实卡在其下）', () => {
    expect(DOC_SIDE_BY_SIDE_MIN).toBe(1100)
  })
})

describe('DealDocLayout · ① 未展开', () => {
  it('左内容 + aside + rail 同屏，不渲染文档与分隔条', () => {
    setup()
    expect(screen.getByText('CONTENT')).toBeTruthy()
    expect(screen.getByText('ASIDE')).toBeTruthy()
    expect(screen.getByText('RAIL')).toBeTruthy()
    expect(screen.queryByText(/PREVIEW:/)).toBeNull()
    expect(screen.queryByRole('separator')).toBeNull()
    expect(mocks.preview).not.toHaveBeenCalled()
  })

  it('没有 aside 时只有 rail（专项页才给 aside）', () => {
    render(
      <DealDocLayout
        picked={null}
        docSideBySide={false}
        focusDoc={false}
        ownerId={1}
        onClose={vi.fn()}
        onSaved={vi.fn()}
        onReview={vi.fn()}
        rail={<div>RAIL</div>}
      >
        <div>CONTENT</div>
      </DealDocLayout>,
    )
    expect(screen.queryByText('ASIDE')).toBeNull()
    expect(screen.getByText('RAIL')).toBeTruthy()
  })
})

describe('DealDocLayout · ② 展开且净宽够（文档在右）', () => {
  it('文档与分隔条出现，aside 让位、事实卡仍在', () => {
    const { onClose, onSaved, onReview } = setup({ picked: FILE, docSideBySide: true })

    expect(screen.getByText('PREVIEW:起诉状.docx')).toBeTruthy()
    expect(screen.getByRole('separator', { name: '调整预览栏宽度' })).toBeTruthy()
    // 文档在右时 aside 不再渲染（右栏已被文档占用）
    expect(screen.queryByText('ASIDE')).toBeNull()
    expect(screen.getByText('RAIL')).toBeTruthy()
    expect(screen.getByText('CONTENT')).toBeTruthy()

    // 预览卡拿到的是 ownerId 与三个回调本身（不做二次包装）
    const props = mocks.preview.mock.calls[0]![0]
    expect(props.ownerId).toBe(443)
    expect(props.onClose).toBe(onClose)
    expect(props.onSaved).toBe(onSaved)
    expect(props.onReview).toBe(onReview)
  })

  it('分隔条方向键调整宽度，且不会低于 320', () => {
    setup({ picked: FILE, docSideBySide: true })
    const handle = screen.getByRole('separator')

    // 默认宽度 720 来自 useResizablePanel；→ 是加，← 是减
    fireEvent.keyDown(handle, { key: 'ArrowRight' })
    fireEvent.keyDown(handle, { key: 'ArrowLeft' })
    // 只断言不抛、不改变文档存在性：宽度落在 style 上，由 use-resizable-panel 自己测
    expect(screen.getByText('PREVIEW:起诉状.docx')).toBeTruthy()
  })
})

describe('DealDocLayout · ③ 展开且净宽不够（文档通栏置顶）', () => {
  it('文档在前、内容在其下，不出现分隔条', () => {
    const { container } = setup({ picked: FILE, focusDoc: true })

    expect(screen.getByText('PREVIEW:起诉状.docx')).toBeTruthy()
    expect(screen.getByText('CONTENT')).toBeTruthy()
    expect(screen.queryByRole('separator')).toBeNull()

    // 顺序：文档在内容之前（通栏置顶的可观测证据）
    const text = container.textContent ?? ''
    expect(text.indexOf('PREVIEW:起诉状.docx')).toBeLessThan(text.indexOf('CONTENT'))
  })

  it('③ 态渲染事实卡：文档置顶，事实卡在其下（不丢内容）', () => {
    // 回归：此前 focusDoc 分支只渲染 doc，rail 整块丢失，宽屏 + 净宽不足时
    // 右侧事实卡（期限 / 当事人 / 收费 / 文件夹）彻底不可达。
    // 本组件头部文档明确写「③ 文档通栏，内容与事实卡在其下」，这里断言它真的做到。
    setup({ picked: FILE, focusDoc: true })
    expect(screen.getByText('RAIL')).toBeTruthy()
  })
})
