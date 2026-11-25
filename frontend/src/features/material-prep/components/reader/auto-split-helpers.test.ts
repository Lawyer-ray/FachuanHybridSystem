/**
 * 自动分段纯逻辑助手单测（node 环境）。
 *
 * 这个文件守的是「自动识别跑起来之后，界面还能说人话」那一层：
 * - 图片来源判型（`guessImageType`）：照片取字前要贴 MIME，判错后端直接拒收；
 * - 提示名清洗（`hintNamesOf`）：材料包标题是连写的中文句子，切错就会把
 *   「（扫描件）」这类复数当成当事人名字；
 * - 分段来源标记（`segmentBackendOf`）：宁可说「规则」，也不能把规则引擎
 *   谎报成 AI 分段——律师据此判断结果要不要重跑；
 * - 轮询（`pollJob`）：超时与心跳停止必须给出能行动的文案，而不是让律师
 *   盯着一个不再动的进度条。
 *
 * 只测对外行为，不测内部实现（`toStage` / `progressTextOf` 走 `jobSnapshotOf`
 * 与 `pollJob` 的可见出口断言）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ getPdfSplitJob: vi.fn() }))
vi.mock('../../api', () => apiMock)

import {
  POLL_LIMIT,
  blocksToMarkdown,
  formatElapsed,
  guessImageType,
  hintNamesOf,
  jobSnapshotOf,
  pipelineProgressPct,
  pollJob,
  ruleSegmentCountOf,
  segmentBackendNote,
  segmentBackendOf,
} from './auto-split-helpers'

/** 按顺序给出任务快照的桩：每次轮询取一条，用尽后重复最后一条 */
function stubJobSequence(jobs: Array<Record<string, unknown>>) {
  let i = 0
  apiMock.getPdfSplitJob.mockImplementation(() => {
    const job = jobs[Math.min(i, jobs.length - 1)]
    i += 1
    return Promise.resolve(job)
  })
}

/** 永不过期、sleep 立即返回的 lease：只关心回调与异常，不关心真实等待 */
function quickLease() {
  return { isStale: () => false, sleep: () => Promise.resolve() }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('guessImageType：文件名 → 图片 MIME', () => {
  /**
   * 后端只存 content_type，缺失时（压缩包展开、老附件）要由文件名补齐；
   * 判成 image/jpeg 但实际是 png，识别端会按 jpeg 解码失败。
   * 所以每个分支都必须对得上，而不是「差不多都是图片」。
   */
  it.each([
    ['证据1.png', 'image/png'],
    ['证据1.webp', 'image/webp'],
    ['证据1.gif', 'image/gif'],
    ['证据1.bmp', 'image/bmp'],
    ['证据1.tif', 'image/tiff'],
    ['证据1.tiff', 'image/tiff'],
    ['IMG_0001.heic', 'image/heic'],
    ['IMG_0001.heif', 'image/heic'],
  ])('%s → %s', (name, mime) => {
    expect(guessImageType(name)).toBe(mime)
  })

  it('未知后缀回落 image/jpeg（手机拍照绝大多数是 jpeg，不能返回空串让 FormData 丢类型）', () => {
    expect(guessImageType('扫描件.jpg')).toBe('image/jpeg')
    expect(guessImageType('扫描件.jpeg')).toBe('image/jpeg')
    // 完全没有扩展名（压缩包展开后偶见）也不能崩
    expect(guessImageType('未命名')).toBe('image/jpeg')
  })

  it('大小写不敏感：相机导出的 IMG_0001.HEIC 不能落进 jpeg 兜底', () => {
    expect(guessImageType('IMG_0001.JPG')).toBe('image/jpeg')
    expect(guessImageType('IMG_0001.HEIC')).toBe('image/heic')
    expect(guessImageType('证据.PNG')).toBe('image/png')
    expect(guessImageType('证据.TIFF')).toBe('image/tiff')
  })
})

describe('hintNamesOf：从标题与文件名取「提示名」', () => {
  /**
   * 材料包标题是「张三诉甲公司借款合同纠纷（扫描件）」这类连写句子，没有词边界。
   * 这里守的是清洗规则本身：去扩展名 / 去括号注释 / 去程序词 / 拆短片段 / 去重。
   * 洗过头会漏掉真名字，洗不够会把「扫描件」当当事人交给下游匹配。
   */
  it('去扩展名与括号注释：「（扫描件）」不算名字', () => {
    const got = hintNamesOf('张三诉甲公司借款合同纠纷（扫描件）', [])
    expect(got).toContain('张三诉甲公司借款合同纠纷')
    expect(got.some((n) => n.includes('扫描件'))).toBe(false)
  })

  it('程序词（诉讼材料 / 卷宗 / 档案…）被剔掉，不残留成候选名', () => {
    const got = hintNamesOf('谭某某借款纠纷诉讼材料卷宗档案', [])
    expect(got.some((n) => n.includes('卷宗') || n.includes('档案') || n.includes('诉讼材料'))).toBe(false)
  })

  it('按中文标点切成最短片段（真名字自然落在某个片段里）', () => {
    const got = hintNamesOf('张三、甲公司 与 李四', [])
    expect(got).toEqual(['张三', '甲公司', '与', '李四'].filter((n) => n.length >= 2))
  })

  it('单字片段被丢弃（一个字的片段当不上名字，只会污染匹配）', () => {
    expect(hintNamesOf('张三、李四、王五', [])).toEqual(['张三', '李四', '王五'])
    const one = hintNamesOf('甲', [])
    expect(one).toEqual([])
  })

  it('纯英文/数字片段被丢弃（提示名只服务中文当事人匹配）', () => {
    expect(hintNamesOf('abc 12345 张三', [])).toEqual(['张三'])
  })

  it('同一名字在标题与多个文件名里重复出现时去重', () => {
    const got = hintNamesOf('张三借款合同纠纷', [
      { n: '张三身份证.png' },
      { n: '材料三：张三', customName: '张三借款合同' },
    ])
    // 「张三借款合同纠纷」/「张三身份证」/「张三」都是不同片段，但「张三」本身只出现一次
    expect(got.filter((n) => n === '张三')).toHaveLength(1)
    expect(new Set(got).size).toBe(got.length)
  })

  it('customName 优先参与清洗（律师改过的名字比原名更可能含真名）', () => {
    const got = hintNamesOf(undefined, [{ n: 'IMG_0001.png', customName: '李四身份证明' }])
    expect(got).toContain('李四身份证明')
    expect(got.some((n) => n.includes('IMG'))).toBe(false)
  })

  it('subject 为 undefined 不崩（材料包可以没有标题）', () => {
    expect(() => hintNamesOf(undefined, [])).not.toThrow()
    expect(hintNamesOf(undefined, [])).toEqual([])
  })

  it('空串标题 / 空串文件名被跳过，不产出空片段', () => {
    expect(hintNamesOf('', [{ n: '' }])).toEqual([])
  })
})

describe('segmentBackendOf：分段来源标记', () => {
  /**
   * 这个标记会显示给律师，用来判断「这份分段是 AI 分的还是规则兜的」，
   * 进而决定要不要重跑。取不到时**必须**说规则（空串），
   * 谎报成 AI 会让一次降级结果被当成正常结果收下。
   */
  it('summary.segment_backend 是字符串时原样返回', () => {
    expect(segmentBackendOf({ summary: { segment_backend: 'llm' } })).toBe('llm')
    expect(segmentBackendOf({ summary: { segment_backend: 'rule' } })).toBe('rule')
  })

  it('非字符串（数字 / null / 对象 / 缺失）一律返回空串，不谎报 AI 分段', () => {
    expect(segmentBackendOf({ summary: { segment_backend: 1 } })).toBe('')
    expect(segmentBackendOf({ summary: { segment_backend: null } })).toBe('')
    expect(segmentBackendOf({ summary: { segment_backend: { v: 'llm' } } })).toBe('')
    expect(segmentBackendOf({ summary: {} })).toBe('')
  })
})

describe('jobSnapshotOf：后端载荷 → 结构化快照', () => {
  it('阶段码按后端枚举收窄，不认识的阶段按「取字」保守处理', () => {
    const base = { job_id: 'j', status: 'processing' }
    expect(jobSnapshotOf({ ...base, stage: 'extract' }).stage).toBe('extract')
    expect(jobSnapshotOf({ ...base, stage: 'cross_check' }).stage).toBe('cross_check')
    expect(jobSnapshotOf({ ...base, stage: 'segment' }).stage).toBe('segment')
    expect(jobSnapshotOf({ ...base, stage: 'done' }).stage).toBe('done')
    // 后端将来加阶段：不丢掉整块面板，按取字显示
    expect(jobSnapshotOf({ ...base, stage: 'brand_new_stage' }).stage).toBe('')
    expect(jobSnapshotOf(base).stage).toBe('')
  })

  it('缺字段时给安全默认值（老任务 / 刚创建）', () => {
    const snap = jobSnapshotOf({ job_id: 'j', status: 'processing' })
    expect(snap.progressPct).toBe(0)
    expect(snap.processedPages).toBe(0)
    expect(snap.totalPages).toBe(0)
    expect(snap.elapsedSeconds).toBeNull()
    expect(snap.staleSeconds).toBeNull()
    expect(snap.errorMessage).toBe('')
    expect(snap.dualEngines).toBe('')
    expect(snap.sourceName).toBe('')
  })
})

describe('pipelineProgressPct：后端 progress 与阶段真实完成度', () => {
  /**
   * 后端取字做完就写 progress=100，但后面还有十几分钟的比对与分段。
   * 这条映射就是「100% 假死」的解法：阶段过了取字，进度条就不再信任 progress。
   */
  it('交叉比对停在 90、分段停在 99，done 才到 100', () => {
    expect(pipelineProgressPct('cross_check', 100)).toBe(90)
    expect(pipelineProgressPct('segment', 100)).toBe(99)
    expect(pipelineProgressPct('done', 0)).toBe(100)
  })

  it('取字阶段折算到 0-90，且被上下夹住', () => {
    expect(pipelineProgressPct('extract', 50)).toBe(45)
    expect(pipelineProgressPct('extract', 100)).toBe(90)
    expect(pipelineProgressPct('extract', -10)).toBe(0)
    expect(pipelineProgressPct('extract', 1000)).toBe(90)
    // progress 拿不到时用页级兜底值
    expect(pipelineProgressPct('extract', 0, 100)).toBe(90)
  })
})

describe('formatElapsed / blocksToMarkdown', () => {
  it('已耗时按中文习惯给（不到一分钟只报秒）', () => {
    expect(formatElapsed(null)).toBe('')
    expect(formatElapsed(-1)).toBe('')
    expect(formatElapsed(Number.NaN)).toBe('')
    expect(formatElapsed(45)).toBe('45 秒')
    expect(formatElapsed(120)).toBe('2 分钟')
    expect(formatElapsed(192)).toBe('3 分 12 秒')
  })

  it('OCR 块只拼文字：空块被丢掉，不产出空行', () => {
    expect(blocksToMarkdown(undefined)).toBe('')
    expect(blocksToMarkdown([{ text: '第一行' }, { text: '  ' }, { text: '第二行' }])).toBe('第一行\n第二行')
  })
})

/**
 * P3-4：图片旁路的阅读顺序。引擎返回的块序不保证是阅读序（手机拍照证据尤其乱），
 * 直接 join 会把上下行、左右块交错在一起——律师拿到的正文读不通，下游 AI 更读不通。
 */
describe('blocksToMarkdown：按坐标重建阅读顺序', () => {
  /** 造一个归一化坐标块（x/y/w/h 都是 0-1） */
  const b = (text: string, x: number, y: number, w = 0.4, h = 0.04) => ({ text, x, y, w, h })

  it('乱序输入按 y 分行、行内按 x 排（不是按返回序）', () => {
    const out = blocksToMarkdown([
      b('第二行左', 0.1, 0.2),
      b('第一行右', 0.5, 0.1),
      b('第二行右', 0.5, 0.2),
      b('第一行左', 0.1, 0.1),
    ])
    expect(out).toBe('第一行左 第一行右\n第二行左 第二行右')
  })

  it('y 有轻微抖动仍归同一行（拍照倾斜/识别框不齐）', () => {
    const out = blocksToMarkdown([b('左', 0.1, 0.1), b('右', 0.6, 0.112), b('下一行', 0.1, 0.2)])
    expect(out).toBe('左 右\n下一行')
  })

  it('行距明显时分行，不会把整页拍成一行', () => {
    const out = blocksToMarkdown([b('一', 0.1, 0.1), b('二', 0.1, 0.16), b('三', 0.1, 0.22)])
    expect(out).toBe('一\n二\n三')
  })

  it('多栏同一 y 上的块按 x 从左到右（栏检测不在本次范围，行为要确定）', () => {
    const out = blocksToMarkdown([b('右栏首行', 0.55, 0.1), b('左栏首行', 0.05, 0.1), b('左栏次行', 0.05, 0.16)])
    expect(out).toBe('左栏首行 右栏首行\n左栏次行')
  })

  it('坐标不全 / 非法时不猜阅读序，保持返回序', () => {
    expect(blocksToMarkdown([{ text: '甲' }, { text: '乙', x: 0.1, y: 0.2 }])).toBe('甲\n乙')
    expect(blocksToMarkdown([b('甲', 0.1, Number.NaN), b('乙', 0.1, 0.2)])).toBe('甲\n乙')
  })

  it('空块与全空白坐标块都丢掉，不产出空行', () => {
    expect(blocksToMarkdown([b('  ', 0.1, 0.1), b('正文', 0.1, 0.2), b('', 0.1, 0.3)])).toBe('正文')
    expect(blocksToMarkdown([])).toBe('')
  })
})

/**
 * P1-9：后端把 summary.segment_backend 写诚实了（全 llm→llm、有规则批→mixed、
 * 全规则→rule）。前端必须认 mixed，并把「几段是规则兜的」说出来——
 * 宁可说规则，也不能把规则引擎说成 LLM。
 */
describe('segmentBackendOf / segmentBackendNote：mixed 三态', () => {
  it('mixed 原样透出（不再被当成非 llm 就整份说成规则）', () => {
    expect(segmentBackendOf({ summary: { segment_backend: 'mixed' } })).toBe('mixed')
  })

  it('全 llm 说律所 AI；全 rule / 缺失说规则引擎', () => {
    expect(segmentBackendNote(['llm', 'llm'], 0)).toBe('律所 AI 分段')
    expect(segmentBackendNote(['rule'], 3)).toBe('规则引擎分段（律所 AI 不可用）；3 段为规则分段请重点复核')
    expect(segmentBackendNote([''], 0)).toBe('规则引擎分段（律所 AI 不可用）')
    expect(segmentBackendNote([], 0)).toBe('')
  })

  it('整本一次（llm_wholebook）也算律所 AI 分段，不能说成规则降级', () => {
    // 回归：只认 'llm' 的写法会把整本分段算进「其余含规则引擎」，把更好的切法说成降级
    expect(segmentBackendNote(['llm_wholebook'], 0)).toBe('律所 AI 分段（整本一次）')
    expect(segmentBackendNote(['llm_wholebook_cross'], 0)).toBe(
      '律所 AI 分段（整本一次 + 交叉核对）；两种切法不一致的段已标「待裁定」',
    )
    expect(segmentBackendNote(['llm_wholebook', 'rule'], 2)).toBe(
      '1/2 律所 AI 分段，其余含规则引擎；2 段为规则分段请重点复核',
    )
  })

  it('mixed 说混合分段并报出规则段数（律师据此重点复核）', () => {
    expect(segmentBackendNote(['mixed'], 4)).toBe('律所 AI 与规则引擎混合分段；4 段为规则分段请重点复核')
    expect(segmentBackendNote(['llm', 'mixed'], 2)).toBe('1/2 律所 AI 分段，其余含规则引擎；2 段为规则分段请重点复核')
    expect(segmentBackendNote(['llm', 'rule'], 5)).toBe('1/2 律所 AI 分段，其余含规则引擎；5 段为规则分段请重点复核')
  })

  it('规则段数按段级 source_method 算；summary 说全规则但一个标记都没有时按整批计', () => {
    const segs = [{ source_method: 'llm' }, { source_method: 'rule' }, { source_method: 'rule' }]
    expect(ruleSegmentCountOf('mixed', segs)).toBe(2)
    expect(ruleSegmentCountOf('llm', segs)).toBe(2)
    expect(ruleSegmentCountOf('rule', [{}, {}])).toBe(2)
    // 来源不明时不猜成规则（宁可少报，也不把 LLM 分段说成规则）
    expect(ruleSegmentCountOf('', [{}, {}])).toBe(0)
    expect(ruleSegmentCountOf('mixed', [{ source_method: 'llm' }])).toBe(0)
  })

  /**
   * 规则引擎不止产出 'rule'：segment_detector.py 还会给 layout_title / rule_weak_only /
   * rule_adjacent_start / rule_merged_adjacent / gap_fill。只认 'rule' 会少报复核段数，
   * 律师以为只有几段要看——这正是本条要防的回归。
   */
  it('规则引擎的多种 source_method 全部计入（不只 rule）', () => {
    const ruleMethods = ['rule', 'layout_title', 'rule_weak_only', 'rule_adjacent_start', 'rule_merged_adjacent', 'gap_fill']
    const segs = ruleMethods.map((m) => ({ source_method: m }))
    expect(ruleSegmentCountOf('mixed', segs)).toBe(ruleMethods.length)
    expect(ruleSegmentCountOf('rule', segs)).toBe(ruleMethods.length)
    // 与 LLM 段混在一起时只数规则那几段
    expect(ruleSegmentCountOf('mixed', [{ source_method: 'llm' }, ...segs])).toBe(ruleMethods.length)
    // 将来新增的规则变体也不该漏（排除法天然覆盖）
    expect(ruleSegmentCountOf('mixed', [{ source_method: 'rule_brand_new' }])).toBe(1)
  })

  it('llm 前缀不计入（后端自己也用 startswith("llm") 判 LLM）', () => {
    expect(ruleSegmentCountOf('llm', [{ source_method: 'llm' }, { source_method: 'llm_merged' }])).toBe(0)
  })

  it('manual（人工确认/新建段）不计入——不能把律师自己分的段说成规则段', () => {
    expect(ruleSegmentCountOf('mixed', [{ source_method: 'manual' }, { source_method: 'manual' }])).toBe(0)
    expect(ruleSegmentCountOf('mixed', [{ source_method: 'manual' }, { source_method: 'rule' }])).toBe(1)
    // 段级标记比 summary 准：summary 说全规则但段级全是人工，就报 0（不按整批兜底）
    expect(ruleSegmentCountOf('rule', [{ source_method: 'manual' }])).toBe(0)
  })

  it('空/空白来源不计入；机械按页切分 page_split 计入（同样不是内容分析结果）', () => {
    expect(ruleSegmentCountOf('mixed', [{ source_method: '' }, { source_method: '   ' }, {}])).toBe(0)
    expect(ruleSegmentCountOf('mixed', [{ source_method: 'page_split' }, { source_method: 'llm' }])).toBe(1)
    // 空白标记不算「有标记」，仍走 summary 兜底
    expect(ruleSegmentCountOf('rule', [{ source_method: '  ' }, {}])).toBe(2)
  })
})

describe('pollJob：阶段文案', () => {
  /**
   * 工具条按钮仍读这条文字。过了取字阶段就不能再说「正在识别 X/Y 页」——
   * 页数早已满了，再报一次只会让人以为进度倒退。
   */
  async function textsOf(jobs: Array<Record<string, unknown>>): Promise<string[]> {
    stubJobSequence([...jobs, { status: 'completed', segments: [], summary: {} }])
    const seen: string[] = []
    await pollJob('job-x', quickLease(), (text: string) => seen.push(text))
    return seen
  }

  it('取字阶段报页数与百分比（有页数）', async () => {
    const texts = await textsOf([
      { job_id: 'job-x', status: 'processing', stage: 'extract', total_pages: 164, processed_pages: 82 },
    ])
    expect(texts).toEqual(['正在识别 82/164 页（50%）'])
  })

  it('取字阶段页数未知时退回报后端 progress', async () => {
    const texts = await textsOf([
      { job_id: 'job-x', status: 'processing', stage: 'extract', total_pages: 0, progress: 37 },
    ])
    expect(texts).toEqual(['正在识别（37%）'])
  })

  it('页数与 progress 都没有时不报空转文案（不产出「正在识别 0/0 页」）', async () => {
    const texts = await textsOf([
      { job_id: 'job-x', status: 'processing', stage: 'extract', total_pages: 0, progress: 0 },
    ])
    expect(texts).toEqual([''])
  })

  it('交叉比对比与分段阶段改说当前在做什么', async () => {
    const texts = await textsOf([
      { job_id: 'job-x', status: 'processing', stage: 'cross_check', total_pages: 164, processed_pages: 164 },
      { job_id: 'job-x', status: 'processing', stage: 'segment', total_pages: 164, processed_pages: 164 },
    ])
    expect(texts).toEqual(['双引擎交叉比对中…', '正在智能分段…'])
  })

  it('done 阶段说「正在收尾…」（回落时不能说成「正在识别 164/164 页」，看着像卡住）', async () => {
    const texts = await textsOf([
      { job_id: 'job-x', status: 'processing', stage: 'done', total_pages: 164, processed_pages: 164 },
    ])
    expect(texts).toEqual(['正在收尾…'])
  })
})

describe('pollJob：心跳停止与超时', () => {
  it('自己发起的任务心跳超过阈值立刻失败，文案给出「已中断 + 怎么重试」', async () => {
    // 900s ≈ 15 分钟无响应：律师要知道「多久没动」和「下一步怎么办」
    stubJobSequence([{ job_id: 'job-s', status: 'processing', stale_seconds: 900 }])
    await expect(pollJob('job-s', quickLease())).rejects.toThrow(/识别进程已中断（15 分钟无响应）/)
    await expect(pollJob('job-s', quickLease())).rejects.toThrow(/请稍后重试；若反复中断，可先拆分页数再识别/)
  })

  it('tolerateStale 时不因心跳停止抛错（接管别人的任务，放弃与否交给用户）', async () => {
    stubJobSequence([
      { job_id: 'job-t', status: 'processing', stale_seconds: 5000 },
      { status: 'completed', segments: [], summary: {} },
    ])
    const job = await pollJob('job-t', quickLease(), undefined, true)
    expect(job.status).toBe('completed')
  })

  it('轮询次数用尽仍未终态 → 超时文案（不能无限等下去）', async () => {
    apiMock.getPdfSplitJob.mockResolvedValue({ job_id: 'job-u', status: 'processing', stage: 'extract' })
    await expect(pollJob('job-u', quickLease())).rejects.toThrow('云端识别等待超时，请稍后重试')
    // 确认真跑满了上限（而不是第一轮就误判超时）
    expect(apiMock.getPdfSplitJob).toHaveBeenCalledTimes(POLL_LIMIT)
  })

  it('失败任务直接抛出后端给出的原因（不吞成「失败」两个字）', async () => {
    apiMock.getPdfSplitJob.mockResolvedValue({
      job_id: 'job-f',
      status: 'failed',
      error_message: '云端 OCR 余额不足',
    })
    await expect(pollJob('job-f', quickLease())).rejects.toThrow('云端 OCR 余额不足')
  })

  it('后端没给原因时按状态说人话，取消不是失败', async () => {
    apiMock.getPdfSplitJob.mockResolvedValue({ job_id: 'job-c', status: 'cancelled' })
    await expect(pollJob('job-c', quickLease())).rejects.toThrow('PDF 拆分任务已取消')

    apiMock.getPdfSplitJob.mockResolvedValue({ job_id: 'job-g', status: 'failed' })
    await expect(pollJob('job-g', quickLease())).rejects.toThrow('PDF 拆分任务失败')
  })

  it('lease 失效时立刻退出（换包 / 卸载后不该继续轮询旧任务）', async () => {
    const lease = { isStale: () => true, sleep: () => Promise.resolve() }
    await expect(pollJob('job-stale', lease)).rejects.toThrow('已取消')
    expect(apiMock.getPdfSplitJob).not.toHaveBeenCalled()
  })

  it('review_required 是终态（等人工复核，不必再轮询）', async () => {
    apiMock.getPdfSplitJob.mockResolvedValue({ job_id: 'job-r', status: 'review_required', segments: [] })
    const job = await pollJob('job-r', quickLease())
    expect(job.status).toBe('review_required')
    expect(apiMock.getPdfSplitJob).toHaveBeenCalledTimes(1)
  })
})
