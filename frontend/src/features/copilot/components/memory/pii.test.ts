/**
 * 策展提升的两条前置拦截：PII 粗筛与原样提升判定。
 *
 * 后端也有同样的闸门（`memory_service.promote_memory`），这里守的是「前端能在
 * 律师提交前给出同一结论」——两侧口径一旦漂移，律师就会看到「明明提示没问题
 * 却被拒」或「原样共享被放行」。
 */
import { describe, expect, it } from 'vitest'

import { normalize, scanPii } from './pii'

describe('scanPii', () => {
  it('干净文本不命中', () => {
    expect(scanPii('回复法院函件控制在 800 字以内')).toEqual([])
  })

  it('手机号命中', () => {
    // PII 检测闸门自身的测试输入
    expect(scanPii('客户手机 13800138000 的案子都可分期')).toEqual(['手机号']) // privacy-allow
  })

  it('18 位身份证号命中（同时命中 16-19 位数字的银行卡规则，两条都提示无妨）', () => {
    // PII 检测闸门自身的测试输入
    expect(scanPii('身份证 110101199003074567 的当事人')) // privacy-allow
      .toEqual(['身份证号', '银行卡号'])
  })

  it('案号（含全角括号）命中', () => {
    // PII 检测闸门自身的测试输入。这里必须保留真实案号的**形状**（年份+法院代字+
    // 字号）否则正则会扫不到，所以用纯虚构的占位值 + privacy-allow 标记。
    expect(scanPii('参见（9999）占0000民初0001号判决')) // privacy-allow
      .toContain('案号')
  })

  it('企业全称命中「完整当事人名称」', () => {
    expect(scanPii('占位测试有限责任公司付款后')).toContain('完整当事人名称')
  })

  it('多条命中时按规则顺序全部报出', () => {
    // 同上：手机号与案号都必须是能命中规则的形状，值为纯虚构占位
    const hits = scanPii('手机 13000000001，另见（9998）占0000民初0002号') // privacy-allow
    expect(hits).toEqual(['手机号', '案号'])
  })
})

describe('normalize（与后端 content_hash_of 同口径）', () => {
  it('折叠连续空白与首尾空白', () => {
    expect(normalize('  回复   函件\n不超过 800 字 ')).toBe('回复 函件 不超过 800 字')
  })

  it('只差首尾空白与连续空白时归一化相等（判定「原样提升」够用）', () => {
    expect(normalize('回复   法院函件\n')).toBe(normalize(' 回复 法院函件 '))
  })
})
