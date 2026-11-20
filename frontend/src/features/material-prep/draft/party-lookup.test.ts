import type { DraftState } from '../types'
import {
  lookupKnownParties,
  mergeKnownParties,
  pickSameParty,
  resolveParties,
  type SearcherHit,
} from './party-lookup'

/**
 * 客户库对账单测（node 环境，注入假 searcher，不发请求）。
 *
 * 断言聚焦三条语义：
 *  ① 客户库认得的一侧以库为准（`is_our_client` 是律师维护过的既成事实）
 *  ② 库给不出答案的一侧退回标签判定，且同一主体不会同时出现在两造
 *  ③ 检索失败 / 认错风险高时宁可不填，也不把错值写进「委托人」
 */

function draftWith(...texts: string[]): DraftState {
  return {
    mats: [],
    segs: texts.map((md, i) => ({ id: `seg-${i}`, t: `段${i}`, fn: `f${i}.pdf`, refs: [], manual: false, md })),
    infos: [],
  }
}

/** 假客户库：名字 → 是否我方当事人 */
function searcherOf(table: Record<string, boolean>) {
  const calls: string[] = []
  const search = async (keyword: string): Promise<SearcherHit[]> => {
    calls.push(keyword)
    return Object.entries(table)
      .filter(([name]) => name.includes(keyword))
      .map(([name, is_our_client]) => ({ name, is_our_client }))
  }
  return { search, calls }
}

/** 工伤复议卷宗的形状：答复书里的申请人是委托单位，工伤认定书里的是职工 */
const GONG_SHANG = draftWith(
  ['# 行政复议答复书', '申请人：某某山庄饮食有限公司'].join('\n'),
  ['# 工伤认定申请表', '申请人：苏某某', '职工姓名：苏某某'].join('\n'),
  ['# 认定工伤决定书', '申请人：苏某某', '职工姓名：苏某某', '用人单位：某某山庄饮食有限公司'].join('\n'),
)

describe('pickSameParty：认同一个人', () => {
  const hits = [
    { name: '苏某某', is_our_client: false },
    { name: '苏某某（已归档）', is_our_client: true },
  ]

  it('优先精确同名', () => {
    expect(pickSameParty('苏某某', hits)).toMatchObject({ name: '苏某某', is_our_client: false })
  })

  it('材料里只写简称时接受「命中名包含候选名」，并用库里全称', () => {
    expect(pickSameParty('某某山庄饮食', [{ name: '佛山市某某山庄饮食有限公司', is_our_client: true }])).toMatchObject(
      { name: '佛山市某某山庄饮食有限公司' },
    )
  })

  it('候选名太短（<4 字）时不认，避免「苏某某」命中「苏某某某」这类跨人', () => {
    expect(pickSameParty('苏某', [{ name: '苏某某', is_our_client: true }])).toBeNull()
  })

  it('没有任何包含关系时返回 null（手机号/证件号撞上的无关命中）', () => {
    expect(pickSameParty('谭某某', [{ name: '李某某', is_our_client: false }])).toBeNull()
  })
})

describe('lookupKnownParties：批量查库', () => {
  it('并发查、去重、按候选顺序返回', async () => {
    const { search, calls } = searcherOf({ 苏某某: false, 某某山庄饮食有限公司: true })
    const found = await lookupKnownParties(['某某山庄饮食有限公司', '苏某某', '某某山庄饮食有限公司'], search)
    expect(calls).toEqual(['某某山庄饮食有限公司', '苏某某'])
    expect(found.map((f) => f.text)).toEqual(['某某山庄饮食有限公司', '苏某某'])
    expect(found.map((f) => f.isOurClient)).toEqual([true, false])
  })

  it('单个查询失败不影响其余候选', async () => {
    const search = async (kw: string): Promise<SearcherHit[]> => {
      if (kw === '苏某某') throw new Error('boom')
      return [{ name: kw, is_our_client: true }]
    }
    const found = await lookupKnownParties(['某某山庄饮食有限公司', '苏某某'], search)
    expect(found).toHaveLength(1)
    expect(found[0]).toMatchObject({ text: '某某山庄饮食有限公司', isOurClient: true })
  })

  it('候选为空时不发请求', async () => {
    const { search, calls } = searcherOf({})
    expect(await lookupKnownParties([], search)).toEqual([])
    expect(calls).toEqual([])
  })
})

describe('mergeKnownParties：库结论优先，标签兜底', () => {
  it('两侧都查到时完全以客户库为准（用库里的全称）', () => {
    const got = mergeKnownParties(
      { our: '苏某某、某某山庄饮食有限公司', their: '' },
      [
        { text: '某某山庄饮食有限公司', canonical: '佛山市某某山庄饮食有限公司', isOurClient: true },
        { text: '苏某某', canonical: '苏某某', isOurClient: false },
      ],
    )
    expect(got).toEqual({ our: '佛山市某某山庄饮食有限公司', their: '苏某某' })
  })

  it('库只给出一侧时，另一侧退回标签判定；已知属于对面的名字从委托人里剔除', () => {
    const got = mergeKnownParties(
      { our: '苏某某、某某山庄饮食有限公司', their: '某某人社局' },
      [{ text: '苏某某', canonical: '苏某某', isOurClient: false }],
    )
    expect(got.our).toBe('某某山庄饮食有限公司')
    expect(got.their).toBe('苏某某')
  })

  it('主公库一条都没查到时原样返回标签判定结果', () => {
    const text = { our: '某某银行', their: '谭某某' }
    expect(mergeKnownParties(text, [])).toBe(text)
  })
})

describe('resolveParties：整条链路（文本 → 客户库 → 合并）', () => {
  it('工伤复议卷宗：客户库把「申请人」两造分开，委托人不再混进职工', async () => {
    const { search } = searcherOf({ 苏某某: false, 某某山庄饮食有限公司: true })
    const got = await resolveParties(GONG_SHANG, search)
    expect(got.our).toBe('某某山庄饮食有限公司')
    expect(got.their).toBe('苏某某')
  })

  it('客户库查不到任何人时等价于纯标签判定（不因为查库而丢掉识别结果）', async () => {
    const got = await resolveParties(GONG_SHANG, async () => [])
    expect(got.our).toBe('某某山庄饮食有限公司')
    expect(got.their).toBe('')
  })

  it('检索整体失败时同样退回标签判定，不抛错', async () => {
    const got = await resolveParties(GONG_SHANG, async () => {
      throw new Error('network down')
    })
    expect(got.our).toBe('某某山庄饮食有限公司')
  })

  it('没有正文时不发请求（未识别的包不该多打一次后端）', async () => {
    const { search, calls } = searcherOf({})
    const got = await resolveParties(draftWith('', '  '), search)
    expect(got).toEqual({ our: '', their: '' })
    expect(calls).toEqual([])
  })
})
