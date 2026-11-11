import type { DraftState } from '../types'
import { applyDetectedParties, detectParties } from './detect-parties'

/**
 * 当事人自动识别单测（node 环境，纯函数）。
 *
 * 断言聚焦三条产品语义，而不是正则细节：
 *  ① 标签优先于裸名字（「催收人：某某」这类内部人员不得成为当事人）
 *  ② 对方优先（同一人同时命中两造标签时归对方，借款人/被告指向性更强）
 *  ③ 回填只填空字段，不覆盖律师已填/已改的内容
 */

/** 只带分段正文的草稿底稿 */
function draftWith(...texts: string[]): DraftState {
  return {
    mats: [],
    segs: texts.map((md, i) => ({ id: `seg-${i}`, t: `段${i}`, fn: `f${i}.pdf`, refs: [], manual: false, md })),
    infos: [],
  }
}

describe('detectParties：标签定位', () => {
  it('按标签分别识别委托人与对方当事人（同侧多个主体跨分段累计）', () => {
    const got = detectParties(
      draftWith(
        ['贷款人（乙方）：某某银行股份有限公司', '借款人（甲方）：谭某某'].join('\n'),
        '报送单位：某某银行某某支行',
      ),
    )
    expect(got.our).toBe('某某银行股份有限公司、某某银行某某支行')
    expect(got.their).toBe('谭某某')
  })

  it('同一份材料里只走一次标签：带括号的长标签优先，值里不留「（甲方）」残渣', () => {
    const got = detectParties(draftWith('借款人（甲方）：谭某某（身份证 110101199305110011）'))
    // 括号说明被截掉，身份证号不会被当成名字
    expect(got.their).toBe('谭某某')
    expect(got.our).toBe('')
  })

  it('内部人员不作为当事人（催收人/经办人/代理人等）', () => {
    const got = detectParties(
      draftWith(['催收人：李催收', '经办人：王经办', '负责人：赵负责', '借款人：谭某某'].join('\n')),
    )
    expect(got.our).toBe('')
    expect(got.their).toBe('谭某某')
  })

  it('标签后面没有冒号不命中（「借款人基本情况」不是当事人行）', () => {
    const got = detectParties(draftWith('借款人基本情况说明'))
    expect(got.their).toBe('')
  })
})

describe('detectParties：清洗与投票', () => {
  it('一行里带多个字段时只取第一个值（全角空格分隔的身份证号被砍掉）', () => {
    const got = detectParties(draftWith('借款人：谭某某\u3000\u3000身份证号：110101199305110011'))
    expect(got.their).toBe('谭某某')
  })

  it('职务尾巴被剥掉（「陈某某 行长」→「陈某某」）', () => {
    const got = detectParties(draftWith('原告：陈某某 行长'))
    expect(got.our).toBe('陈某某')
  })

  it('出现频次高者优先，跨分段累计投票', () => {
    const got = detectParties(
      draftWith(
        ['借款人：谭某某', '抵押人：梁某某'].join('\n'),
        ['借款人：谭某某', '借款人：谭某某'].join('\n'),
      ),
    )
    // 谭某某 3 票 > 梁某某 1 票，但两者都进名单且谭在前
    expect(got.their.split('、')[0]).toBe('谭某某')
    expect(got.their.split('、')).toContain('梁某某')
  })

  it('一批超过 3 个名字时只保留票数最高的 3 个', () => {
    const got = detectParties(
      draftWith(
        [
          '被告：甲某某',
          '被告：乙某某',
          '被告：乙某某',
          '被告：丙某某',
          '被告：丙某某',
          '被告：丁某某',
          '被告：丁某某',
        ].join('\n'),
      ),
    )
    const names = got.their.split('、')
    expect(names).toHaveLength(3)
    expect(names).not.toContain('甲某某')
  })

  it('我方名单剔掉已在对方名单出现的名字（同一人不可能在两造）', () => {
    const got = detectParties(draftWith(['借款人：谭某某', '委托人：谭某某', '委托人：某某银行'].join('\n')))
    expect(got.their).toBe('谭某某')
    expect(got.our).toBe('某某银行')
  })

  it('没有可用正文（md 为空 / segs 为空）时两侧都为空串，不猜', () => {
    expect(detectParties(draftWith())).toEqual({ our: '', their: '' })
    expect(detectParties(draftWith('', '   '))).toEqual({ our: '', their: '' })
  })
})

describe('applyDetectedParties：只填空字段', () => {
  const field = (k: string, v = '', src = '') => ({ k, v, src, srcRef: null })

  it('空字段回填并标来源「自动识别」，已填字段原样保留', () => {
    const infos = [field('委托人'), field('对方当事人', '律师手填的人', '手工')]
    const { infos: next, changed } = applyDetectedParties(infos, { our: '某某银行', their: '谭某某' })
    expect(changed).toBe(true)
    expect(next[0]).toMatchObject({ k: '委托人', v: '某某银行', src: '自动识别' })
    // 已有值不覆盖
    expect(next[1]).toEqual(infos[1])
  })

  it('识别结果为空时不填（空的输入框比填错的好），也不报改动', () => {
    const infos = [field('委托人'), field('对方当事人')]
    const { infos: next, changed } = applyDetectedParties(infos, { our: '', their: '' })
    expect(changed).toBe(false)
    // 无改动时返回同一引用，避免触发多余保存
    expect(next).toBe(infos)
  })

  it('与当事人无关的字段不被改动', () => {
    const infos = [field('案由'), field('标的额')]
    const { changed, infos: next } = applyDetectedParties(infos, { our: '某某银行', their: '谭某某' })
    expect(changed).toBe(false)
    expect(next).toBe(infos)
  })

  it('只有一侧识别到时也只填那一侧', () => {
    const infos = [field('委托人'), field('对方当事人')]
    const { infos: next, changed } = applyDetectedParties(infos, { our: '', their: '谭某某' })
    expect(changed).toBe(true)
    expect(next[0]).toEqual(field('委托人'))
    expect(next[1]).toMatchObject({ v: '谭某某', src: '自动识别' })
  })
})
