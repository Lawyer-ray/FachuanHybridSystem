// @vitest-environment jsdom
/**
 * DraftDialog（一句话生成文书）单测。
 *
 * 锁住四条行为，每条都对应一个真实误用后果：
 * 1) 类型下拉必须来自 `doc-types`（不是前端写死的常量）；
 * 2) 成功 → 关弹窗 + 回调 `(file_url, subpath)` + 「填充率 N%」成功提示；
 * 3) 失败（HTTP 200 + created=false）→ **不关弹窗**且 reason 原文可见——
 *    这是律师唯一能看懂失败原因、并自己去补文件夹模板的地方；
 * 4) 有未决槽 → warning 提示里带条数（不是伪装成完全成功）；
 * 5) 判断说 blocked → 主按钮改成「仍然生成草稿（留空处会挂批注）」并以 force=true 下发；
 * 6) 判断请求本身失败（网络/500）→ **不挡起草**：一行可读错误 + 主按钮变「直接生成」。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const listDocTypesMock = vi.hoisted(() => vi.fn())
const draftByTypeMock = vi.hoisted(() => vi.fn())
const assessReadinessMock = vi.hoisted(() => vi.fn())

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  listDocTypes: listDocTypesMock,
  draftByType: draftByTypeMock,
  assessDraftReadiness: assessReadinessMock,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

import { toast } from 'sonner'

import type { DraftAssessResult, DraftResult } from '../types'
import { DraftDialog } from './DraftDialog'

const DOC_TYPES = [
  { doc_type: 'jurisdiction_objection', display_name: '管辖权异议申请书', family: 'litigation_v1' },
  { doc_type: 'complaint', display_name: '民事起诉状', family: 'litigation_v1' },
]

function result(over: Partial<DraftResult> = {}): DraftResult {
  return {
    created: true,
    doc_type: 'jurisdiction_objection',
    kind: 'case',
    owner_id: 399,
    name: '管辖权异议申请书.docx',
    subpath: '2-诉状/管辖权异议申请书.docx',
    file_url: '/api/v1/cases/399/folder-file?subpath=2-%E8%AF%89%E7%8A%B6',
    filled: {},
    pending: [],
    slot_fill_rate: 0.8,
    review_run_id: null,
    warnings: [],
    reason: '',
    ...over,
  }
}

/** 立案前判断的最小出参：默认 blocked（这一档才改变主按钮行为） */
function readiness(over: Partial<DraftAssessResult> = {}): DraftAssessResult {
  return {
    verdict: 'blocked',
    profile_key: 'lease_arrears',
    matrix: [],
    missing_materials: [
      {
        item: '被告身份证复印件或户籍信息',
        why: '立案需明确被告并送达',
        from_whom: '委托人 / 律师调查',
        form: '复印件 / 公安查询单',
        severity: 'blocking',
      },
    ],
    questions: [],
    blocking: ['被告身份证复印件或户籍信息'],
    warnings: [],
    ...over,
  }
}

function setup(over: { onCreated?: (u: string, s: string) => void } = {}) {
  const onOpenChange = vi.fn()
  const onCreated = over.onCreated ?? vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <DraftDialog open onOpenChange={onOpenChange} caseId={399} onCreated={onCreated} />
    </QueryClientProvider>,
  )
  return { onOpenChange, onCreated }
}

/** 选类型 → 点「生成」。类型清单是异步的，必须先等到 option 出现再改值 */
async function pickTypeAndSubmit() {
  await pickType()
  fireEvent.click(screen.getByRole('button', { name: '生成' }))
}

/** 只选类型（不动按钮）：留给需要先判断再决定的用例 */
async function pickType() {
  await screen.findByRole('option', { name: '管辖权异议申请书' })
  fireEvent.change(screen.getByTestId('draft-doc-type'), { target: { value: 'jurisdiction_objection' } })
}

beforeEach(() => {
  listDocTypesMock.mockReset()
  listDocTypesMock.mockResolvedValue(DOC_TYPES)
  draftByTypeMock.mockReset()
  assessReadinessMock.mockReset()
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.warning).mockClear()
  vi.mocked(toast.error).mockClear()
})

describe('DraftDialog', () => {
  it('类型下拉渲染后端返回的文书类型', async () => {
    setup()
    expect(await screen.findByRole('option', { name: '管辖权异议申请书' })).toBeTruthy()
    expect(screen.getByRole('option', { name: '民事起诉状' })).toBeTruthy()
  })

  it('生成成功：回调 file_url + subpath、关弹窗、报填充率', async () => {
    draftByTypeMock.mockResolvedValue(result())
    const { onOpenChange, onCreated } = setup()

    await pickTypeAndSubmit()

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(result().file_url, result().subpath))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
      '已生成《管辖权异议申请书.docx》，填充率 80%',
      expect.anything(),
    )
    // 入参按冻结接口下发：案件侧、自动审查、facts 留空交模型写
    expect(draftByTypeMock).toHaveBeenCalledWith(
      expect.objectContaining({ doc_type: 'jurisdiction_objection', case_id: 399, auto_review: true, facts: {} }),
    )
  })

  it('失败（created=false）：不关弹窗，并原样显示后端 reason', async () => {
    const reason = '案件 399 没有匹配的文件夹模板，无法确定文书落在哪个目录'
    draftByTypeMock.mockResolvedValue(result({ created: false, subpath: '', name: '', reason }))
    const { onOpenChange, onCreated } = setup()

    await pickTypeAndSubmit()

    expect(await screen.findByText(reason)).toBeTruthy()
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled()
  })

  it('没选文书类型时「先看材料够不够」不可点，选了就可用', async () => {
    setup()
    const button = screen.getByTestId('draft-assess') as HTMLButtonElement
    expect(button.disabled).toBe(true)

    await pickType()

    expect(button.disabled).toBe(false)
  })

  it('判断为 blocked：结论一句话，主按钮改成「仍然生成草稿」并以 force=true 下发', async () => {
    assessReadinessMock.mockResolvedValue(readiness())
    draftByTypeMock.mockResolvedValue(result())
    setup()

    await pickType()
    fireEvent.click(screen.getByTestId('draft-assess'))

    expect((await screen.findByTestId('readiness-verdict')).textContent).toBe('现在还不能出，缺 1 项')
    expect(assessReadinessMock).toHaveBeenCalledWith(expect.objectContaining({ case_id: 399 }))

    fireEvent.click(screen.getByRole('button', { name: '仍然生成草稿（留空处会挂批注）' }))

    await waitFor(() =>
      expect(draftByTypeMock).toHaveBeenCalledWith(
        expect.objectContaining({ doc_type: 'jurisdiction_objection', force: true }),
      ),
    )
  })

  it('判断请求失败不挡起草：给一行错误 + 主按钮变「直接生成」（force 保持 false）', async () => {
    assessReadinessMock.mockRejectedValue(new Error('判断服务 500'))
    draftByTypeMock.mockResolvedValue(result())
    setup()

    await pickType()
    fireEvent.click(screen.getByTestId('draft-assess'))

    const failure = await screen.findByTestId('draft-assess-failure')
    expect(failure.textContent).toContain('材料判断没跑成功')
    expect(failure.textContent).toContain('判断服务 500')

    fireEvent.click(screen.getByRole('button', { name: '直接生成' }))

    await waitFor(() =>
      expect(draftByTypeMock).toHaveBeenCalledWith(expect.objectContaining({ force: false })),
    )
  })

  it('有未决槽：warning 提示列出条数（不当成完全成功）', async () => {
    draftByTypeMock.mockResolvedValue(result({ pending: ['court_name', 'judge_name'], slot_fill_rate: 0.6 }))
    setup()

    await pickTypeAndSubmit()

    await waitFor(() =>
      expect(vi.mocked(toast.warning)).toHaveBeenCalledWith(
        '有 2 项未决，成稿里是空的',
        expect.anything(),
      ),
    )
  })
})
