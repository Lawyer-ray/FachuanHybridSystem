/**
 * 归案 → 发起审查的接线（node 环境）。
 *
 * `useAssignLaunch` 名字带 use、但**不读任何 React 状态**（纯闭包 + 入参），
 * 所以直接调用即可，不需要 renderHook；辅助函数也按 hook 命名（`useSetup`）
 * 以通过 lint 的 rules-of-hooks 检查。
 *
 * 这个 hook 是「律师以为点了一下，其实后端建了客户/合同/案件/材料」的那条链路。
 * 它的错法几乎都不报错：
 *
 * - `partiesOf` 的索引对齐错了（多了一个空当事人），甲乙丙丁就会错位，
 *   建出来的案件把对方当事人记成我方；
 * - 归案成功后**跳错 id 空间**：`/projects/:id` 是合同 id、`/bank-litigation/:id`
 *   是案件 id，拿 caseId 去拼项目详情会打开别人家的合同（踩过，报「合同 482
 *   不存在」）；
 * - `onStarted` 在没有项目锚点时仍跳复审台，跳过去是一张空表；
 * - `onAssignConfirm` 吞掉异常，用户以为归案成功。
 *
 * 所以这里断言的是「参数归谁、跳哪条路径、说什么话」，不做组件渲染。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    warning: vi.fn(),
  }),
}))

vi.mock('../../api', () => ({
  assignPack: vi.fn(),
  fetchAttachmentBytes: vi.fn(),
}))

import { toast } from 'sonner'

import { assignPack, fetchAttachmentBytes } from '../../api'
import type { AssignInfo, DraftState } from '../../types'
import { loadDocxBytes, partiesOf, useAssignLaunch } from './use-assign-launch'

const assignPackMock = vi.mocked(assignPack)
const fetchBytesMock = vi.mocked(fetchAttachmentBytes)

/** 最小可用草稿：两段（各自单源连续）、四条当事人字段、两份素材 */
function draft(over: Partial<DraftState> = {}): DraftState {
  return {
    mats: [
      { partIndex: 0, n: '卷一.pdf', k: 'pdf', pages: 10 },
      { partIndex: 1, n: '卷二.pdf', k: 'pdf', pages: 6 },
    ],
    segs: [
      { id: 's1', t: '起诉状', fn: 'a.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false },
      { id: 's2', t: '', fn: 'b.pdf', refs: [{ mi: 1, p: 1 }], manual: false },
    ],
    infos: [
      { k: '委托人', v: '某某公司', src: 'ocr', srcRef: null },
      { k: '对方当事人', v: '李某', src: 'ocr', srcRef: null },
      { k: '标的额', v: '120000', src: 'ocr', srcRef: null },
      { k: '案由', v: '金融借款合同纠纷', src: 'ocr', srcRef: null },
    ],
    ...over,
  } as DraftState
}

/** 造 hook 的一整套依赖桩，返回它们以便断言（本 hook 不读 React 状态，可直接调用） */
function useSetup(params: { projectId?: number; draft?: DraftState | null } = {}) {
  const deps = {
    draft: params.draft === undefined ? draft() : params.draft,
    messageId: 77,
    projectId: params.projectId,
    navigate: vi.fn(),
    setAssignOpen: vi.fn(),
    setAssign: vi.fn(),
    close: vi.fn(),
    setLaunchFile: vi.fn(),
  }
  const hook = useAssignLaunch(deps)
  return { deps, hook }
}

const okResult = {
  caseId: 31,
  caseName: '李某某某公司金融借款合同纠纷',
  contractId: 482,
  boundCount: 2,
  unsplitCount: 0,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('partiesOf：甲乙丙丁的对齐', () => {
  it('按 infos 顺序映射到 party_a..party_d', () => {
    expect(partiesOf(draft())).toEqual({
      party_a: '某某公司',
      party_b: '李某',
      party_c: '120000',
      party_d: '金融借款合同纠纷',
    })
  })

  it('空值与纯空白跳过，不能被当成一个空当事人塞进去', () => {
    // 跳过而不是留空串：后端会为空名创建客户，案件里就多一个没有名字的当事人
    const d = draft({
      infos: [
        { k: '委托人', v: '  ', src: '', srcRef: null },
        { k: '对方当事人', v: ' 李某 ', src: '', srcRef: null },
      ] as DraftState['infos'],
    })
    expect(partiesOf(d)).toEqual({ party_b: '李某' })
  })

  it('超过 4 条时索引越界回落成 party_a（不允许拼出 party_e 这种后端不认的键）', () => {
    const d = draft({
      infos: Array.from({ length: 6 }, (_, i) => ({
        k: `字段${i}`,
        v: `值${i}`,
        src: '',
        srcRef: null,
      })) as DraftState['infos'],
    })
    const parties = partiesOf(d)
    // 键只可能有 party_a..party_d（后端不认 party_e）
    expect(Object.keys(parties)).toEqual(['party_a', 'party_b', 'party_c', 'party_d'])
    // 第 4 条（索引 3）落到 party_d；越界的第 5、6 条回落 party_a 并覆盖前者
    expect(parties.party_d).toBe('值3')
    expect(parties.party_a).toBe('值5')
  })

  it('值两端空白被 trim（后端按名字建客户，带空白会建成两家）', () => {
    const d = draft({
      infos: [{ k: '委托人', v: '  某某公司  ', src: '', srcRef: null }] as DraftState['infos'],
    })
    expect(partiesOf(d).party_a).toBe('某某公司')
  })
})

describe('loadDocxBytes', () => {
  it('按文件名找到素材后取其 partIndex 的字节', async () => {
    fetchBytesMock.mockResolvedValue(new ArrayBuffer(8))
    await loadDocxBytes(77, draft(), '卷二.pdf')
    expect(fetchBytesMock).toHaveBeenCalledWith(77, 1)
  })

  it('材料包里找不到该文件名时抛错（不能静默返回空字节让后端去猜）', async () => {
    await expect(loadDocxBytes(77, draft(), '不存在.docx')).rejects.toThrow('材料包里找不到该文件')
    expect(fetchBytesMock).not.toHaveBeenCalled()
  })
})

describe('onStarted：审查启动后的落点', () => {
  it('有项目锚点：跳复审台（/projects/:id/review/:taskId）', () => {
    const { deps, hook } = useSetup({ projectId: 393 })
    hook.onStarted('task-9')

    expect(deps.navigate).toHaveBeenCalledWith('/projects/393/review/task-9')
    expect(deps.setLaunchFile).toHaveBeenCalledWith(null)
    expect(deps.close).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('审查已启动', { description: '正在打开复审工作台…' })
  })

  it('没有项目锚点：不跳转，改为说清「请到项目下查看」', () => {
    const { deps, hook } = useSetup()
    hook.onStarted('task-9')

    // 无锚点时跳复审台会落在一张空表上，用户完全不知道发生了什么
    expect(deps.navigate).not.toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('审查已启动', {
      description: '材料尚未归属到具体项目，请到项目下查看复审工作台',
    })
  })

  it('onCloseDrawer 只清 launchFile 并关闭，不导航', () => {
    const { deps, hook } = useSetup({ projectId: 393 })
    hook.onCloseDrawer()
    expect(deps.setLaunchFile).toHaveBeenCalledWith(null)
    expect(deps.close).toHaveBeenCalled()
    expect(deps.navigate).not.toHaveBeenCalled()
  })
})

describe('onAssignConfirm：成功路径', () => {
  const assignNew: AssignInfo = { target: 'new' }

  it('点确认先关弹窗并落归案表单（用户在等待期间能看到自己的选择）', async () => {
    assignPackMock.mockResolvedValue(okResult)
    const { deps, hook } = useSetup()
    await hook.onAssignConfirm(assignNew)

    expect(deps.setAssignOpen).toHaveBeenCalledWith(false)
    expect(deps.setAssign).toHaveBeenCalledWith(assignNew)
    expect(toast.loading).toHaveBeenCalledWith('正在归案…', { id: 'assign' })
  })

  it('新建案件：案件名 = 当事人 + 案由（褪掉旧的年份后缀）', async () => {
    assignPackMock.mockResolvedValue(okResult)
    const { hook } = useSetup()
    await hook.onAssignConfirm(assignNew)

    const arg = assignPackMock.mock.calls[0]![0]
    // 「李某金融借款合同纠纷」——既不带年份也不把「案件」当后缀，列表里一眼能认
    expect(arg.caseName).toBe('李某金融借款合同纠纷')
    expect(arg.cause).toBe('金融借款合同纠纷')
    expect(arg.targetAmount).toBe('120000')
    expect(arg.parties).toEqual({ our: '某某公司', their: '李某' })
    expect(arg.messageId).toBe(77)
  })

  it('段名与页范围按 refs 首尾推导（段名空时用文件名）', async () => {
    assignPackMock.mockResolvedValue(okResult)
    const { hook } = useSetup()
    await hook.onAssignConfirm(assignNew)

    expect(assignPackMock.mock.calls[0]![0].segments).toEqual([
      { name: '起诉状', partIndex: 0, pageStart: 1, pageEnd: 2 },
      // 段名空 → 用文件名
      { name: 'b.pdf', partIndex: 1, pageStart: 1, pageEnd: 1 },
    ])
  })

  it('已有案件（target=existing）时 caseName 为 undefined（后端用已有案件名）', async () => {
    assignPackMock.mockResolvedValue({ ...okResult, contractId: null })
    const { hook } = useSetup()
    await hook.onAssignConfirm({ target: 'existing', caseId: 31 })

    expect(assignPackMock.mock.calls[0]![0].caseName).toBeUndefined()
    expect(assignPackMock.mock.calls[0]![0].caseId).toBe(31)
  })

  it('成功后跳到**合同**详情（:id 是合同 id，不是案件 id）', async () => {
    assignPackMock.mockResolvedValue(okResult)
    const { deps, hook } = useSetup()
    await hook.onAssignConfirm(assignNew)

    // /projects/:id 的 :id 必须是合同 id；传 caseId 会打开别人家的合同
    expect(deps.navigate).toHaveBeenCalledWith('/projects/482')
    expect(deps.setAssign).toHaveBeenLastCalledWith({ ...assignNew, caseId: 31, caseTitle: okResult.caseName })
  })

  it('没有合同（建合同失败）时退回办案详情（按案件 id 看）', async () => {
    assignPackMock.mockResolvedValue({ ...okResult, contractId: null })
    const { deps, hook } = useSetup()
    await hook.onAssignConfirm(assignNew)

    expect(deps.navigate).toHaveBeenCalledWith('/bank-litigation/31')
  })

  it('绑定数 > 0 时说「已绑定 N 份」，否则说清「建了案但材料没绑上」', async () => {
    assignPackMock.mockResolvedValue(okResult)
    const first = useSetup()
    await first.hook.onAssignConfirm(assignNew)
    expect(toast.success).toHaveBeenLastCalledWith(`已归案到「${okResult.caseName}」`, {
      id: 'assign',
      description: '已绑定 2 份材料，可到办案详情查看',
      duration: 5000,
    })

    assignPackMock.mockResolvedValue({ ...okResult, boundCount: 0 })
    const second = useSetup()
    await second.hook.onAssignConfirm(assignNew)
    expect(toast.success).toHaveBeenLastCalledWith(`已归案到「${okResult.caseName}」`, {
      id: 'assign',
      description: '案件已创建，但材料绑定未成功 —— 可到办案详情手动上传',
      duration: 5000,
    })
  })
})

describe('onAssignConfirm：拒绝与失败', () => {
  it('有跨源合并的段时拦住归案，并点名是哪几份（宁可拦住也不默默丢证据）', async () => {
    const bad = draft({
      segs: [
        // A 的 1-2 页 + B 的第 1 页：三字段模型表达不了，切出来会丢掉 B 那几页
        { id: 's1', t: '证据一', fn: 'a.pdf', refs: [{ mi: 0, p: 1 }, { mi: 1, p: 1 }], manual: false },
      ] as DraftState['segs'],
    })
    const { hook } = useSetup({ draft: bad })
    await hook.onAssignConfirm({ target: 'new' })

    expect(assignPackMock).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith(
      '有材料跨了多个源文件，无法直接归案',
      expect.objectContaining({ id: 'assign', description: expect.stringContaining('a.pdf') }),
    )
  })

  it('归案请求失败：toast 说清「归案失败：后端原因」，不暴露技术堆栈', async () => {
    assignPackMock.mockRejectedValue({ name: 'HTTPError', data: { message: '材料包已被删除' } })
    const { deps, hook } = useSetup()
    await hook.onAssignConfirm({ target: 'new' })

    // 吞掉异常会让用户以为归案成功（列表里却没有案件），这是曾经的真实问题
    expect(toast.error).toHaveBeenCalledWith('归案失败：材料包已被删除', { id: 'assign', duration: 6000 })
    expect(deps.navigate).not.toHaveBeenCalled()
  })

  it('草稿还没就绪（draft=null）时也能走通：段为空、当事人为空', async () => {
    assignPackMock.mockResolvedValue({ ...okResult, boundCount: 0 })
    const { deps, hook } = useSetup({ draft: null })
    await hook.onAssignConfirm({ target: 'new' })

    const arg = assignPackMock.mock.calls[0]![0]
    expect(arg.segments).toEqual([])
    expect(arg.sources).toEqual([])
    expect(arg.parties).toEqual({ our: '', their: '' })
    // 没有当事人时案件名回落「新收材料 + 默认案由」
    expect(arg.caseName).toBe('新收材料金融借款合同纠纷')
    // 空草稿没有页可切，归案本身仍要成功，只是不绑材料
    expect(deps.setAssign).toHaveBeenCalled()
  })
})
