// @vitest-environment jsdom
/**
 * MetaPanel 测试（jsdom）。
 *
 * 材料信息便签面板。核心分支：
 * - 空态只显示「便签，不是表单」；有字段后让位
 * - 字段类型派发：select（有 opts）/ textarea（ta）/ PartyPicker（当事人三类）/ 普通 input
 * - 删除两段确认：有值先 arm、再点才删；空值直接删；blur 取消 arm
 * - 标来源按钮的 pressed 态与切换
 * - 「记一项」展开字段库、已用字段不重复出现、用完提示
 */
import { fireEvent, render, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../constants', () => ({
  FIELD_LIB: [
    { k: '委托人', ph: '姓名或单位' },
    { k: '对方当事人', ph: '对方' },
    { k: '标的额', ph: '金额' },
  ],
}))
vi.mock('./PartyPicker', () => ({
  PartyPicker: ({ value, placeholder }: { value: string; placeholder?: string }) => (
    <div>
      PARTY_PICKER:{value}:{placeholder}
    </div>
  ),
}))

import type { PageQualityByMi } from '../../types'
import { MetaPanel } from './MetaPanel'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function draft(infos: unknown[]) {
  return { mats: [], segs: [], infos } as never
}

function ops() {
  return {
    setValue: vi.fn(),
    removeInfo: vi.fn(),
    addInfo: vi.fn(),
  }
}

function renderPanel(
  infos: unknown[],
  extra: {
    pickInfo?: number
    o?: ReturnType<typeof ops>
    onRedetectParties?: () => void
    redetectBusy?: boolean
  } = {},
) {
  const o = extra.o ?? ops()
  const onSetPickInfo = vi.fn()
  const utils = render(
    wrap(
      <MetaPanel
        draft={draft(infos)}
        pickInfo={extra.pickInfo ?? -1}
        onSetPickInfo={onSetPickInfo}
        ops={o as never}
        focusedSeg={0}
        mdOpen={false}
        onToggleMdOpen={() => {}}
        focusedBlockKey={null}
        onLocateBlock={() => {}}
        onRedetectParties={extra.onRedetectParties}
        redetectBusy={extra.redetectBusy}
      />,
    ),
  )
  return { ...utils, o, onSetPickInfo }
}

/** 字段卡里的「重新识别当事人」按钮（委托人 + 对方当事人各一个；取第一个，没有则为 null） */
function redetectBtn(container: HTMLElement) {
  const all = within(container).queryAllByLabelText('重新识别当事人') as HTMLButtonElement[]
  return all[0] ?? null
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MetaPanel：空态与字段渲染', () => {
  it('无字段时显示便签说明', () => {
    const { container } = renderPanel([])
    expect(container.textContent).toContain('便签，不是表单')
    container.remove()
  })

  it('有字段后不再显示便签说明', () => {
    const { container } = renderPanel([{ k: '标的额', v: '100' }])
    expect(container.textContent).not.toContain('便签，不是表单')
    container.remove()
  })

  it('渲染字段名与值', () => {
    const { container } = renderPanel([{ k: '标的额', v: '100000' }])
    expect(within(container).getByText('标的额')).toBeTruthy()
    // 普通字段的值绑在 input.value 上，不在 textContent 里
    expect((container.querySelector('input') as HTMLInputElement).value).toBe('100000')
    container.remove()
  })

  it('带 src 时显示来源', () => {
    const { container } = renderPanel([{ k: '标的额', v: '1', src: 'P3' }])
    expect(container.textContent).toContain('来源 P3')
    container.remove()
  })
})

describe('MetaPanel：字段类型派发', () => {
  it('有 opts 的字段渲染为 select', () => {
    const { container } = renderPanel([{ k: '类型', v: '', opts: ['民事', '刑事'] }])
    expect(container.querySelector('select')).toBeTruthy()
    container.remove()
  })

  it('ta 标记的字段渲染为 textarea', () => {
    const { container } = renderPanel([{ k: '备注', v: '', ta: true }])
    expect(container.querySelector('textarea')).toBeTruthy()
    container.remove()
  })

  it('委托人渲染为 PartyPicker（我方）', () => {
    const { container } = renderPanel([{ k: '委托人', v: '张三' }])
    expect(container.textContent).toContain('PARTY_PICKER:张三')
    container.remove()
  })

  it('对方当事人渲染为 PartyPicker（非我方）', () => {
    const { container } = renderPanel([{ k: '对方当事人', v: '李四' }])
    expect(container.textContent).toContain('PARTY_PICKER:李四')
    container.remove()
  })

  it('普通字段渲染为 input，输入调用 setValue', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '' }], { o })
    const input = container.querySelector('input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '200' } })
    expect(o.setValue).toHaveBeenCalledWith(0, '200')
    container.remove()
  })

  it('placeholder 合并 ph 与 hint', () => {
    const { container } = renderPanel([{ k: '标的额', v: '', ph: '金额', hint: '含税' }])
    const input = container.querySelector('input') as HTMLInputElement
    expect(input.placeholder).toBe('金额，含税')
    container.remove()
  })
})

describe('MetaPanel：标来源', () => {
  it('未取字时按钮为「标来源」，点击开启', () => {
    const { container, onSetPickInfo } = renderPanel([{ k: '标的额', v: '' }])
    const btn = within(container).getByRole('button', { name: '标来源' })
    fireEvent.click(btn)
    expect(onSetPickInfo).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('取字中时按钮为「取消标来源」且 aria-pressed', () => {
    const { container, onSetPickInfo } = renderPanel([{ k: '标的额', v: '' }], { pickInfo: 0 })
    const btn = within(container).getByRole('button', { name: '取消标来源' })
    expect(btn.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(btn)
    expect(onSetPickInfo).toHaveBeenCalledWith(-1)
    container.remove()
  })
})

describe('MetaPanel：删除两段确认', () => {
  it('有值的字段第一次点击只 arm，不删除', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '100' }], { o })
    const del = within(container).getByRole('button', { name: '删除这个字段' })

    fireEvent.click(del)
    expect(o.removeInfo).not.toHaveBeenCalled()
    container.remove()
  })

  it('有值的字段第二次点击才真正删除', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '100' }], { o })
    const del = within(container).getByRole('button', { name: '删除这个字段' })

    fireEvent.click(del)
    fireEvent.click(del)
    expect(o.removeInfo).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('空值字段直接删除（无需确认）', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '' }], { o })
    fireEvent.click(within(container).getByRole('button', { name: '删除这个字段' }))
    expect(o.removeInfo).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('blur 取消已 arm 的状态', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '100' }], { o })
    const del = within(container).getByRole('button', { name: '删除这个字段' })

    fireEvent.click(del) // arm
    fireEvent.blur(del) // 取消
    fireEvent.click(del) // 重新 arm（若上一步没取消，这次就会删）
    expect(o.removeInfo).not.toHaveBeenCalled()
    container.remove()
  })
})

describe('MetaPanel：记一项字段库', () => {
  it('点「记一项」展开字段库', () => {
    const { container } = renderPanel([])
    fireEvent.click(within(container).getByText('记一项'))
    expect(within(container).getByText('委托人')).toBeTruthy()
    container.remove()
  })

  it('已用字段不出现在字段库里', () => {
    const { container } = renderPanel([{ k: '委托人', v: '张三' }])
    fireEvent.click(within(container).getByText('记一项'))
    // 「委托人」作为已用字段只出现在字段卡里，字段库按钮里不应再有
    const libButtons = Array.from(container.querySelectorAll('button')).filter((b) =>
      ['委托人', '对方当事人', '标的额'].includes(b.textContent ?? ''),
    )
    expect(libButtons.map((b) => b.textContent)).toEqual(['对方当事人', '标的额'])
    container.remove()
  })

  it('点字段库项调用 addInfo 并收起', () => {
    const o = ops()
    const { container } = renderPanel([], { o })
    fireEvent.click(within(container).getByText('记一项'))
    fireEvent.click(within(container).getByText('标的额'))

    expect(o.addInfo).toHaveBeenCalledWith(expect.objectContaining({ k: '标的额' }))
    // 收起后字段库按钮消失
    expect(container.textContent).not.toContain('对方当事人')
    container.remove()
  })

  it('字段库用完时提示', () => {
    const { container } = renderPanel([
      { k: '委托人', v: '' },
      { k: '对方当事人', v: '' },
      { k: '标的额', v: '' },
    ])
    fireEvent.click(within(container).getByText('记一项'))
    expect(container.textContent).toContain('字段库已用完')
    container.remove()
  })
})

describe('MetaPanel：重新识别当事人', () => {
  it('只给当事人字段入口，其余字段没有', () => {
    const { container } = renderPanel([{ k: '标的额', v: '100' }], { onRedetectParties: () => {} })
    expect(redetectBtn(container)).toBeNull()
    container.remove()

    const withParty = renderPanel([{ k: '委托人', v: '某个错的人' }], { onRedetectParties: () => {} })
    expect(redetectBtn(withParty.container)).toBeTruthy()
    withParty.container.remove()
  })

  it('点一下就触发重跑（不需要先清空字段）', () => {
    const onRedetectParties = vi.fn()
    const { container } = renderPanel(
      [
        { k: '委托人', v: '苏某某、某某山庄饮食有限公司', src: '自动识别' },
        { k: '对方当事人', v: '' },
      ],
      { onRedetectParties },
    )
    // 两个当事人字段各有一个入口：重跑的是「整份材料」的识别，点哪个都一样
    expect(within(container).queryAllByLabelText('重新识别当事人')).toHaveLength(2)
    fireEvent.click(redetectBtn(container)!)
    expect(onRedetectParties).toHaveBeenCalledTimes(1)
    container.remove()
  })

  it('没有回调（旧调用方 / 无识别语境的宿主）时不渲染入口', () => {
    const { container } = renderPanel([{ k: '委托人', v: '张三' }])
    expect(redetectBtn(container)).toBeNull()
    container.remove()
  })

  it('重跑中按钮禁用，防连点打爆客户库', () => {
    const onRedetectParties = vi.fn()
    const { container } = renderPanel([{ k: '委托人', v: '张三' }], {
      onRedetectParties,
      redetectBusy: true,
    })
    const btn = redetectBtn(container)!
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(onRedetectParties).not.toHaveBeenCalled()
    container.remove()
  })
})

/**
 * 右栏是「页级识别风险」到达律师眼前的最后一公里：草稿里的 `pageAnomalyByMi` 必须被
 * 算成本段覆盖的页（`degeneratePagesOf` / `columnAnomalyPagesOf` + `columnAnomalyOf`
 * 取详情）再交给正文面板。这里锁的就是这段接线——纯函数本身在 draft 层已单独测过。
 */
describe('MetaPanel：页级识别风险接到正文面板', () => {
  const segWithBody = {
    id: 's1',
    t: '证据',
    fn: '证据一',
    refs: [{ mi: 0, p: 3 }],
    manual: false,
    md: '# 证据目录\n\n原告提交了转账凭证。',
    blocks: [
      {
        page: 3,
        type: 'paragraph',
        text: '原告提交了转账凭证。',
        rect: { x: 0.1, y: 0.2, w: 0.5, h: 0.05, approx: false, precision: 'exact' },
      },
    ],
  }

  function renderWithDraft(pageAnomaly: Record<string, unknown> | undefined) {
    return render(
      wrap(
        <MetaPanel
          draft={{ mats: [], segs: [segWithBody], infos: [], ...(pageAnomaly ? { pageAnomalyByMi: { '0': pageAnomaly } } : {}) } as never}
          pickInfo={-1}
          onSetPickInfo={vi.fn()}
          ops={ops() as never}
          focusedSeg={0}
          mdOpen
          onToggleMdOpen={() => {}}
          focusedBlockKey={null}
          onLocateBlock={() => {}}
        />,
      ),
    )
  }

  it('退化页落成本段页提示（按 seg.refs 求交集，不是全卷照搬）', () => {
    const { container } = renderWithDraft({ degenerate_pages: [3, 12] })
    const hint = container.querySelector('[data-degenerate-hint]') as HTMLElement
    expect(hint).toBeTruthy()
    expect(hint.textContent).toContain('已换识别路径重取')
    // P12 不在本段 refs 里 → 不在这里出提示
    expect(container.querySelectorAll('[data-degenerate-hint]')).toHaveLength(1)
    container.remove()
  })

  it('列数突变页带出「本页几列 vs 上一页几列」的详情', () => {
    const { container } = renderWithDraft({
      column_anomalies: [{ page_no: 3, prev_page_no: 2, cols: 5, prev_cols: 4 }],
    })
    const hint = container.querySelector('[data-column-anomaly-hint]') as HTMLElement
    expect(hint.textContent).toBe('P3 表格 5 列，上一页 P2 为 4 列 · 列可能被并/拆或换了模板，请核对数字表头')
    container.remove()
  })

  it('旧任务草稿没有 pageAnomaly 时正文里不多一条提示（与改动前逐字一致）', () => {
    const { container } = renderWithDraft(undefined)
    expect(container.querySelector('[data-degenerate-hint]')).toBeNull()
    expect(container.querySelector('[data-column-anomaly-hint]')).toBeNull()
    container.remove()
  })
})

/**
 * 页级质量（图纸 / 证件缺字段）同样要走到正文面板的逐页提示，而且必须按**源**求交集：
 * 一个材料包可以有多份 PDF，页号各自从 1 开始，A 份的 P3 信号不能贴到 B 份的 P3 上。
 */
describe('MetaPanel：页级质量按源接到正文面板', () => {
  /** 这一段只引用**第二份**源（mi=1）的第 3 页 */
  const segOfSourceB = {
    id: 's2',
    t: '证据',
    fn: '证据二',
    refs: [{ mi: 1, p: 3 }],
    manual: false,
    md: '# 证据目录\n\n原告提交了转账凭证。',
    blocks: [
      { page: 3, type: 'paragraph', text: '原告提交了转账凭证。', rect: { x: 0.1, y: 0.2, w: 0.5, h: 0.05, approx: false, precision: 'exact' } },
    ],
  }

  function renderWithQuality(pageQualityByMi: PageQualityByMi | null) {
    return render(
      wrap(
        <MetaPanel
          draft={{ mats: [], segs: [segOfSourceB], infos: [] } as never}
          pageQualityByMi={pageQualityByMi}
          pickInfo={-1}
          onSetPickInfo={vi.fn()}
          ops={ops() as never}
          focusedSeg={0}
          mdOpen
          onToggleMdOpen={() => {}}
          focusedBlockKey={null}
          onLocateBlock={() => {}}
        />,
      ),
    )
  }

  it('A 份（mi=0）P3 的图纸页 / 证件页提示不出现在 B 份（mi=1）的 P3 段上', () => {
    const { container } = renderWithQuality({
      '0': {
        graphic_pages: [3],
        doc_hints: { '3': 'id_card' },
        doc_missing: { '3': { doc: 'id_card', missing: ['姓名'] } },
      },
    })
    expect(container.querySelector('[data-quality-hint]')).toBeNull()
    expect(container.querySelector('[data-doc-hint]')).toBeNull()
    container.remove()
  })

  it('同一份源（mi=1）的提示照常出', () => {
    const { container } = renderWithQuality({ '1': { graphic_pages: [3] } })
    const hint = container.querySelector('[data-quality-hint]') as HTMLElement
    expect(hint.textContent).toContain('P3 疑似图纸 / 照片')
    container.remove()
  })

  it('旧草稿（没有 pageQualityByMi）时正文里不多一条提示（与改动前逐字一致）', () => {
    const { container } = renderWithQuality(null)
    expect(container.querySelector('[data-quality-hint]')).toBeNull()
    expect(container.querySelector('[data-doc-hint]')).toBeNull()
    expect(container.querySelector('[data-degenerate-hint]')).toBeNull()
    expect(container.querySelector('[data-column-anomaly-hint]')).toBeNull()
    container.remove()
  })
})
