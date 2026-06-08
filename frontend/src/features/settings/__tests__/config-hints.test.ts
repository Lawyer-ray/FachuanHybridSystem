import { CATEGORY_HINTS } from '../constants/config-hints'

describe('CATEGORY_HINTS', () => {
  it('exports an object with category keys', () => {
    expect(typeof CATEGORY_HINTS).toBe('object')
    expect(Object.keys(CATEGORY_HINTS).length).toBeGreaterThan(0)
  })

  it('contains feishu category with correct structure', () => {
    const feishu = CATEGORY_HINTS.feishu
    expect(feishu).toBeDefined()
    expect(feishu.title).toBe('飞书配置')
    expect(feishu.description).toContain('飞书')
    expect(feishu.fieldOrder).toContain('FEISHU_APP_ID')
    expect(feishu.fields).toBeDefined()
    expect(feishu.fields!.FEISHU_APP_ID!.label).toBe('App ID')
  })

  it('contains dingtalk category', () => {
    const dingtalk = CATEGORY_HINTS.dingtalk
    expect(dingtalk).toBeDefined()
    expect(dingtalk.title).toBe('钉钉配置')
    expect(dingtalk.fields!.DINGTALK_APP_KEY!.label).toBe('App Key')
  })

  it('contains ai category with groups', () => {
    const ai = CATEGORY_HINTS.ai
    expect(ai).toBeDefined()
    expect(ai.title).toBe('AI 服务配置')
    expect(ai.groups).toBeDefined()
    expect(ai.groups!.length).toBeGreaterThan(0)
    expect(ai.groups![0].label).toBe('全局 LLM 设置')
  })

  it('contains ocr category', () => {
    const ocr = CATEGORY_HINTS.ocr
    expect(ocr).toBeDefined()
    expect(ocr.title).toBe('OCR 服务配置')
    expect(ocr.fields!.OCR_PROVIDER!.placeholder).toContain('local')
  })

  it('contains system category', () => {
    const system = CATEGORY_HINTS.system
    expect(system).toBeDefined()
    expect(system.title).toBe('系统连接')
    expect(system.fields!._BACKEND_URL!.label).toBe('后端地址')
  })

  it('each category has title and description', () => {
    for (const [key, cat] of Object.entries(CATEGORY_HINTS)) {
      expect(cat.title).toBeTruthy()
      expect(cat.description).toBeTruthy()
    }
  })
})
