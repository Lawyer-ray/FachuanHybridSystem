// @vitest-environment jsdom
/**
 * DealDocLayout：详情页「内容 / 档案卡 / 文档」的三态布局。
 *
 * 三态是这一层存在的全部理由，所以逐态钉住（漏一个就会出现「文档没处放」或
 * 「档案卡被同一块 DOM 渲染两次」）：
 * - ① 未展开（picked=null）：内容 + aside/rail 同屏，分隔条不出现
 * - ② 展开 + 净宽够（docSideBySide）：内容 + 右文档 + 分隔条，档案卡沉到内容列底部
 * - ③ 展开 + 净宽不够 / 沉浸：文档占满整宽置顶，内容与档案卡在其下
 *
 * 另外钉住两条「不能靠条件渲染」的约束（都和 OnlyOffice 画布有关）：
 * - 文档列始终是容器的最后一个孩子，靠 `order-first` 排到视觉最前——
 *   换 DOM 位次会让 DS 实例销毁重建，未保存的编辑直接丢
 * - 分隔条常驻，只用 className 隐显，不参与兄弟节点数量的变化
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  preview: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('./FilePreviewCard', () => ({
  FilePreviewCard: (props: {
    file: { name: string }
    kind?: string
    ownerId: number
    immersive?: boolean
    onToggleImmersive?: () => void
    onClose: () => void
    onSaved: () => void
    onReview?: (f: { subpath: string; name: string }) => void
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
    ownerId: 443,
    onClose: vi.fn(),
    onSaved: vi.fn(),
    onReview: vi.fn(),
    rail: <div>RAIL</div>,
    aside: <div>ASIDE</div>,
    ...over,
  }
  const view = render(
    <DealDocLayout {...handlers}>
      <div>CONTENT</div>
    </DealDocLayout>,
  )
  return { ...handlers, ...view }
}

/** 分隔条：隐藏时仍挂在 DOM 里，只是带 `hidden` 类（见文件头注释） */
function separator() {
  return screen.getByRole('separator', { name: '调整预览栏宽度' })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('DOC_SIDE_BY_SIDE_MIN', () => {
  it('并排门槛是 1100（低于它文档占满整宽、排到内容之上）', () => {
    expect(DOC_SIDE_BY_SIDE_MIN).toBe(1100)
  })
})

describe('DealDocLayout · ① 未展开', () => {
  it('内容 + aside + rail 同屏，不渲染文档与可拖分隔条', () => {
    setup()
    expect(screen.getByText('CONTENT')).toBeTruthy()
    expect(screen.getByText('ASIDE')).toBeTruthy()
    expect(screen.getByText('RAIL')).toBeTruthy()
    expect(screen.queryByText(/PREVIEW:/)).toBeNull()
    expect(separator().className).toContain('hidden')
    expect(mocks.preview).not.toHaveBeenCalled()
  })

  it('没有 aside 时只有 rail（诉讼页不给 aside）', () => {
    setup({ aside: undefined })
    expect(screen.queryByText('ASIDE')).toBeNull()
    expect(screen.getByText('RAIL')).toBeTruthy()
  })
})

describe('DealDocLayout · ② 展开且净宽够（文档在右）', () => {
  it('文档与分隔条出现，aside 让位、档案卡与内容仍在', () => {
    const { onClose, onSaved, onReview } = setup({ picked: FILE, docSideBySide: true })

    expect(screen.getByText('PREVIEW:起诉状.docx')).toBeTruthy()
    expect(separator().className).not.toContain('hidden')
    // 文档在右时 aside 不再渲染（右栏已被文档占用）
    expect(screen.queryByText('ASIDE')).toBeNull()
    expect(screen.getByText('RAIL')).toBeTruthy()
    expect(screen.getByText('CONTENT')).toBeTruthy()

    // 预览卡拿到的是 ownerId、通道与三个回调本身（不做二次包装）
    const props = mocks.preview.mock.calls[0]![0]
    expect(props.ownerId).toBe(443)
    expect(props.kind).toBe('contract')
    expect(props.immersive).toBe(false)
    expect(props.onClose).toBe(onClose)
    expect(props.onSaved).toBe(onSaved)
    expect(props.onReview).toBe(onReview)
  })

  it('案件文件夹的文档走 case 通道（诉讼页案件卡的文件夹）', () => {
    setup({ picked: FILE, docSideBySide: true, kind: 'case', ownerId: 9, onReview: undefined })
    const props = mocks.preview.mock.calls[0]![0]
    expect(props.kind).toBe('case')
    expect(props.ownerId).toBe(9)
    expect(props.onReview).toBeUndefined()
  })

  it('分隔条方向键调整宽度，且不会把文档调没', () => {
    setup({ picked: FILE, docSideBySide: true })
    const handle = separator()

    // 默认宽度 720 来自 useResizablePanel；→ 是加，← 是减
    fireEvent.keyDown(handle, { key: 'ArrowRight' })
    fireEvent.keyDown(handle, { key: 'ArrowLeft' })
    expect(screen.getByText('PREVIEW:起诉状.docx')).toBeTruthy()
  })
})

describe('DealDocLayout · ③ 展开且净宽不够（文档占满整宽）', () => {
  it('文档排到视觉最前、分隔条收起，内容与档案卡都在其下', () => {
    const { container } = setup({ picked: FILE, docSideBySide: false })

    expect(screen.getByText('PREVIEW:起诉状.docx')).toBeTruthy()
    expect(screen.getByText('CONTENT')).toBeTruthy()
    expect(screen.getByText('RAIL')).toBeTruthy()
    expect(separator().className).toContain('hidden')

    // 「视觉最前」靠 order-first，DOM 位次不变（见文件头注释）
    const docColumn = screen.getByText('PREVIEW:起诉状.docx').closest('.order-first')
    expect(docColumn).not.toBeNull()
    expect(docColumn!.className).toContain('w-full')
    // 文档列是容器最后一个孩子：内容列在前，画布永远不换位次
    expect(container.firstElementChild!.lastElementChild).toBe(docColumn)
  })

  it('档案卡沉到内容列底部（同屏可滚到，不丢内容）', () => {
    setup({ picked: FILE, docSideBySide: false })
    const content = screen.getByText('CONTENT')
    const rail = screen.getByText('RAIL')
    // RAIL 在同一个内容列里、排在 CONTENT 之后
    expect(content.parentElement).toBe(rail.parentElement)
    expect(content.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('DealDocLayout · ③ 沉浸态', () => {
  it('沉浸时文档同样占满整宽，并把开关与状态传给预览卡', () => {
    const onToggleImmersive = vi.fn()
    setup({ picked: FILE, docSideBySide: true, immersive: true, onToggleImmersive })

    expect(screen.getByText('PREVIEW:起诉状.docx').closest('.order-first')).not.toBeNull()
    expect(separator().className).toContain('hidden')
    const props = mocks.preview.mock.calls[0]![0]
    expect(props.immersive).toBe(true)
    expect(props.onToggleImmersive).toBe(onToggleImmersive)
  })

  it('没有文档时沉浸不成立（残留的 true 不该把下一份直接铺满）', () => {
    setup({ picked: null, immersive: true })
    expect(screen.queryByText(/PREVIEW:/)).toBeNull()
    expect(screen.getByText('RAIL')).toBeTruthy()
  })
})
