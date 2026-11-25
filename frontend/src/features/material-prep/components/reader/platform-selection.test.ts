/**
 * 解析平台多选口径的纯逻辑测试。
 *
 * 重点在**传参**而不只是勾选：多选最终要变成 `cloud_backend`（单值正主）+
 * `dual_engines`（逗号分隔）两个字段。`cloud_backend` 只认单值——把逗号串塞进去
 * 会被后端 `resolve_cloud_backends` 当成未知值按 auto 静默降级，用户勾的引擎
 * 就白勾了。所以这组用例把三种选择数量下的输出逐条钉死。
 */
import { describe, expect, it } from 'vitest'

import {
  cloudSelectionSummary,
  crossChecks,
  normalizeCloudSelection,
  resolveBackendRequest,
  serializeDualEngines,
  toggleCloudEngine,
} from './platform-selection'

describe('normalizeCloudSelection：收窄不可信来源', () => {
  it('非数组一律当空集合（旧会话留下的 "auto" 也在内）', () => {
    expect(normalizeCloudSelection('auto')).toEqual([])
    expect(normalizeCloudSelection(undefined)).toEqual([])
    expect(normalizeCloudSelection(null)).toEqual([])
  })

  it('丢掉未知引擎名，保留已知的', () => {
    expect(normalizeCloudSelection(['mineru', 'aliyun', 42])).toEqual(['mineru'])
  })

  it('去重并按固定顺序（MinerU → PaddleOCR-VL → Textin）排列', () => {
    expect(normalizeCloudSelection(['textin', 'mineru', 'mineru'])).toEqual(['mineru', 'textin'])
  })
})

describe('toggleCloudEngine：勾上 / 取消', () => {
  it('勾上返回新数组（zustand 靠引用变化触发订阅）', () => {
    const before: ReturnType<typeof normalizeCloudSelection> = []
    const after = toggleCloudEngine(before, 'mineru')
    expect(after).toEqual(['mineru'])
    expect(after).not.toBe(before)
  })

  it('再点一次取消', () => {
    expect(toggleCloudEngine(['mineru', 'textin'], 'mineru')).toEqual(['textin'])
  })
})

describe('crossChecks：勾两个才比对', () => {
  it('0 / 1 个都不比对', () => {
    expect(crossChecks([])).toBe(false)
    expect(crossChecks(['mineru'])).toBe(false)
  })

  it('2 个及以上比对', () => {
    expect(crossChecks(['mineru', 'paddleocr_vl'])).toBe(true)
    expect(crossChecks(['mineru', 'paddleocr_vl', 'textin'])).toBe(true)
  })
})

describe('resolveBackendRequest：选中集合 → 请求参数', () => {
  it('一个都不勾：cloud_backend=auto（沿用容灾），不发 dual_engines', () => {
    expect(resolveBackendRequest([])).toEqual({ cloudBackend: 'auto', dualEngines: null })
  })

  it('勾一个：锁定该引擎，不发 dual_engines', () => {
    expect(resolveBackendRequest(['textin'])).toEqual({ cloudBackend: 'textin', dualEngines: null })
  })

  it('勾两个：正主优先 MinerU，dual_engines 带全部所选', () => {
    expect(resolveBackendRequest(['paddleocr_vl', 'mineru'])).toEqual({
      cloudBackend: 'mineru',
      dualEngines: ['mineru', 'paddleocr_vl'],
    })
  })

  it('dual_engines 按固定顺序排，与勾选先后无关', () => {
    // 勾选顺序不该影响发出的串：同样的两个引擎，两次勾出同一个值
    expect(resolveBackendRequest(['textin', 'mineru']).dualEngines).toEqual(['mineru', 'textin'])
    expect(resolveBackendRequest(['mineru', 'textin']).dualEngines).toEqual(['mineru', 'textin'])
  })

  it('PaddleOCR-VL 永远不做正主：后端枚举里根本没有这个值', () => {
    // 有可注册平台时优先它（mineru > textin）
    expect(resolveBackendRequest(['paddleocr_vl', 'textin']).cloudBackend).toBe('textin')

    // 只勾 VL 时**退回 auto**，而不是让它当正主。
    //
    // 曾经这里断言的是 'paddleocr_vl'——那是错的，因为后端根本没有这个值：
    //   · DocumentParseProvider.ProviderType 只有 mineru / textin；
    //   · PdfSplitCloudBackend 的合法值也只有 auto / mineru / textin；
    //   · PdfSplitJobService._normalize_cloud_backend('paddleocr_vl') → 'auto'
    //     （与 'bogus' 这类脏值同一档：非法值一律落回 auto）。
    // 发一个后端永远认不出的值，用户以为「锁定了 VL」，实际拿到的是 auto
    // 挑的一个**别的**平台——锁定语义静默失效，比直接退回 auto 更糟。
    // VL 的正确位置是 dual_engines（参与比对），那一路不经过 cloud_backend。
    expect(resolveBackendRequest(['paddleocr_vl']).cloudBackend).toBe('auto')
    // 但单独勾 VL 时不足 2 个引擎，不构成比对，dual_engines 仍是 null
    expect(resolveBackendRequest(['paddleocr_vl']).dualEngines).toBeNull()
  })
})

describe('serializeDualEngines：表单串', () => {
  it('≥2 个引擎时用逗号分隔', () => {
    expect(serializeDualEngines(['mineru', 'paddleocr_vl'])).toBe('mineru,paddleocr_vl')
  })

  it('0 / 1 个引擎时为 null（不发这个字段）', () => {
    expect(serializeDualEngines([])).toBeNull()
    expect(serializeDualEngines(['mineru'])).toBeNull()
  })
})

describe('cloudSelectionSummary：悬浮说明里的选择描述', () => {
  it('空 / 单 / 双三种说法', () => {
    expect(cloudSelectionSummary([])).toBe('自动容灾')
    expect(cloudSelectionSummary(['mineru'])).toBe('仅 MinerU')
    expect(cloudSelectionSummary(['mineru', 'paddleocr_vl'])).toBe('双引擎 · MinerU+VL')
  })

  it('VL 用短名：悬浮说明是单行，全名会把版面策略挤掉', () => {
    expect(cloudSelectionSummary(['paddleocr_vl', 'textin'])).toBe('双引擎 · VL+Textin')
  })
})

describe('DeepSeek 只能单独用，不参与交叉比对', () => {
  // 后端 `DUAL_ENGINE_CHOICES` 里没有 deepseek：它没有独立于 cloud_backend 的第二条
  // 通道。前端若还按「勾两个就比对」显示「将交叉比对」，就是在承诺一件不会发生的事。
  it('只勾 DeepSeek：它就是正主，不发 dual_engines', () => {
    expect(resolveBackendRequest(['deepseek'])).toEqual({ cloudBackend: 'deepseek', dualEngines: null })
  })

  it('DeepSeek + MinerU：正主仍是 MinerU，dual_engines 不含 DeepSeek', () => {
    expect(resolveBackendRequest(['mineru', 'deepseek'])).toEqual({
      cloudBackend: 'mineru',
      dualEngines: null,
    })
  })

  it('DeepSeek + 两个可比对引擎：比对名单里只有那两个', () => {
    const req = resolveBackendRequest(['mineru', 'paddleocr_vl', 'deepseek'])
    expect(req.cloudBackend).toBe('mineru')
    expect(req.dualEngines).toEqual(['mineru', 'paddleocr_vl'])
  })

  it('勾了 DeepSeek 不构成「交叉比对」', () => {
    expect(crossChecks(['mineru', 'deepseek'])).toBe(false)
    expect(crossChecks(['mineru', 'textin', 'deepseek'])).toBe(true)
  })

  it('收窄时保留 deepseek，并排在最后', () => {
    expect(normalizeCloudSelection(['deepseek', 'mineru'])).toEqual(['mineru', 'deepseek'])
  })

  it('摘要要说清「DeepSeek 仅兜底」，不能让用户以为开了比对', () => {
    expect(cloudSelectionSummary(['mineru', 'deepseek'])).toContain('DeepSeek 仅兜底')
    expect(cloudSelectionSummary(['deepseek'])).toBe('仅 DeepSeek')
  })
})
