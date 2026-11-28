// @vitest-environment jsdom
/**
 * CaseOverview（多程序线案件总览）渲染单测。
 *
 * 覆盖：一案一行、程序线小链点（关系已知才有多点）、默认分组随数据变（案由多样按案由、
 * 案由单一时按程序）、点行回跳。这是 261/271/系列案三种形态的共同出口。
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DealCase } from '../../types'
import { CaseOverview } from './CaseOverview'

function makeCase(over: Partial<DealCase> = {}): DealCase {
  return {
    id: 1,
    name: '案件',
    proc: '一审',
    prev: null,
    ref: '',
    numbers: [],
    st: '在办',
    done: false,
    auth: '',
    auths: [],
    cause: '',
    target: null,
    preserv: null,
    from: '',
    partyRows: [],
    parties: [],
    logs: [],
    logReminders: [],
    contacts: [],
    ...over,
  }
}

describe('CaseOverview（一个委托下多条程序线）', () => {
  it('一案一行；串过 previous_case 的两案画成一条小链，孤立案件只画自己那一个点', () => {
    render(
      <CaseOverview
        cases={[
          makeCase({ id: 305, name: '三水南钢上诉升平百货', proc: '二审', cause: '买卖合同纠纷' }),
          makeCase({ id: 361, name: '同艾堂执行三水南钢', proc: '执行', prev: 305, cause: '买卖合同纠纷' }),
          makeCase({ id: 375, name: '梁伟龙上诉升平公司', proc: '二审', cause: '买卖合同纠纷' }),
        ]}
        onJump={() => {}}
      />,
    )
    expect(screen.getByText('3 个案件')).toBeTruthy()
    const execRow = screen.getByTitle('跳到 同艾堂执行三水南钢')
    // 执行那行带整条线：二审 → 执行（这是 ×N 讲不清的那件事）
    expect(within(execRow).getByText('二审')).toBeTruthy()
    expect(within(execRow).getByText('执行')).toBeTruthy()
    // 孤立二审只有自己的点，不能把它接到别人的执行上
    const loneRow = screen.getByTitle('跳到 梁伟龙上诉升平公司')
    expect(within(loneRow).queryByText('执行')).toBeNull()
  })

  it('案由只有一种时默认按程序分组（按案由分就是一整块，等于没分）', () => {
    render(
      <CaseOverview
        cases={[
          makeCase({ id: 1, name: '对甲的一审', proc: '一审', done: true, cause: '买卖合同纠纷' }),
          makeCase({ id: 2, name: '对乙的一审', proc: '一审', done: true, cause: '买卖合同纠纷' }),
          makeCase({ id: 3, name: '执行甲', proc: '执行', cause: '买卖合同纠纷' }),
          makeCase({ id: 4, name: '执行乙', proc: '执行', cause: '买卖合同纠纷' }),
        ]}
        onJump={() => {}}
      />,
    )
    const card = screen.getByText('4 个案件').closest('section') as HTMLElement
    expect(within(card).getByText('2 在办 · 2 已结')).toBeTruthy()
    // 组序走程序序（一审 → 执行），不是拼音序
    expect(within(card).getAllByRole('heading', { level: 4 }).map((h) => h.textContent)).toEqual(['一审', '执行'])
  })

  it('点行把该案 id 交给页面（页面负责滚动 + 高亮）', () => {
    const onJump = vi.fn()
    render(
      <CaseOverview
        cases={[makeCase({ id: 7, name: '刘某某诉奥创民间借贷纠纷' }), makeCase({ id: 8, name: '黄某诉奥创劳动纠纷' })]}
        onJump={onJump}
      />,
    )
    screen.getByTitle('跳到 黄某诉奥创劳动纠纷').click()
    expect(onJump).toHaveBeenCalledWith(8)
  })

  it('没填案由的案件不会消失：落进「未填案由」组', () => {
    render(
      <CaseOverview
        cases={[
          makeCase({ id: 1, name: '有案由', cause: '买卖合同纠纷' }),
          makeCase({ id: 2, name: '没案由', cause: '' }),
        ]}
        onJump={() => {}}
      />,
    )
    expect(screen.getByTitle('跳到 没案由')).toBeTruthy()
    expect(screen.getByText('未填案由')).toBeTruthy()
  })
})
