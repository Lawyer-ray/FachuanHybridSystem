/**
 * 合同审查 API 层的路径与参数锁定（node 环境）。
 *
 * 这层的每个函数都只是一句「拼路径 + post body」，看起来没什么可测——但这里
 * 的错**全部是静默的**：路径拼错会 404，参数归属错（把 task_id 当 contract_id
 * 传）可能命中另一个资源甚至别人的文件，而 tsc/lint 一个字都不会说。
 *
 * 四条主线：
 * 1. prefix 必须完整带 `/api/v1`（`createApiClient` 的 prefix 是**覆盖**而非拼接，
 *    见 payment-intake/api.test.ts 的来龙去脉）；
 * 2. taskId / revisionId 必须 `encodeURIComponent` —— 后端 id 是 UUID，但
 *    材料预处理会把带 `/` 和空格的产物名拼进 task id，不编码就会被路由拆成
 *    多段，请求打到不存在的路径；
 * 3. `suggest / apply / task/apply` 三个端点路径与归属参数（contract_id /
 *    case_id vs task_id）不能混；
 * 4. `uploadContract` 的 modelName 为空串时**不 append** 该字段（空串会让后端
 *    「指定了空模型」而不是「用默认模型」）。
 *
 * 装配方式：`reviewApi()` 是**懒建**的（模块加载时不建客户端），所以拿不到
 * 「实例」来提前挂桩。这里改成按 prefix 把客户端工厂整体换成一个记录器，
 * 用例直接读记录器的调用记录——不依赖调用顺序，也不需要先触发一次建实例。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

/** 记录器：一个 prefix 一条，方法只记调用并返回链式桩 */
type Recorder = {
  prefix: string
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

const recorders = vi.hoisted(() => [] as Recorder[])

/** 客户端工厂换成记录器：get/post 返回可 `.json()` 的 thenable */
vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    const prefix = opts?.prefix ?? '/api/v1'
    const existing = recorders.find((r) => r.prefix === prefix)
    if (existing) return existing
    const respond = () => {
      const p = Promise.resolve({})
      return Object.assign(p, { json: () => p })
    }
    const recorder: Recorder = {
      prefix,
      get: vi.fn(() => respond()),
      post: vi.fn(() => respond()),
    }
    recorders.push(recorder)
    return recorder
  },
}))

import * as api from './api'

function contractReview(): Recorder {
  const r = recorders.find((x) => x.prefix === '/api/v1/contract-review')
  if (!r) throw new Error('contract-review 客户端未创建')
  return r
}

/** 取最近一次 post 的 (path, options) */
function lastPost() {
  const calls = contractReview().post.mock.calls
  return calls[calls.length - 1] as [string, Record<string, unknown>]
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('contract-review api：prefix 与编码', () => {
  it('prefix 是完整的 /api/v1/contract-review（覆盖语义，不能只写 /contract-review）', async () => {
    await api.listRevisions('t-1')
    // prefix 缺 /api/v1 时所有端点会一起 404，而 tsc/lint 全绿
    // （与 payment-intake/api.test.ts 记下的是同一个坑）
    expect(contractReview().prefix).toBe('/api/v1/contract-review')
  })

  it('taskId 里的 / 与空格必须被编码（否则路由把它拆成多段，404）', async () => {
    await api.listRevisions('材料 包/2026 卷宗')
    // 关键在 `/`（%2F）：不编码时它会被当成路径分隔符，`.../revisions`
    // 变成第 4 段，后端路由匹配不到；中文与空格同理要编码
    expect(contractReview().get).toHaveBeenCalledWith(
      '%E6%9D%90%E6%96%99%20%E5%8C%85%2F2026%20%E5%8D%B7%E5%AE%97/revisions',
      { signal: undefined },
    )
  })

  it('revisionId 单独编码：里面出现 / 时不能吃掉路径尾段的 /resolve', async () => {
    await api.resolveRevision('t-1', 'r 2/3', 'accept')
    const [path] = lastPost()
    expect(path).toBe('t-1/revisions/r%202%2F3/resolve')
  })

  it('signal 原样透传（react-query 靠它取消在飞请求）', async () => {
    const ac = new AbortController()
    await api.getTaskStatus('t-1', ac.signal)
    expect(contractReview().get).toHaveBeenCalledWith('t-1/status', { signal: ac.signal })
  })
})

describe('contract-review api：修订清单与状态端点', () => {
  it('getContentVersion 与 listVersions 是两个不同端点（混用会让画布该重建时不重建）', async () => {
    await api.getContentVersion('t-1')
    expect(contractReview().get).toHaveBeenLastCalledWith('t-1/content-version', { signal: undefined })
    await api.listVersions('t-1')
    expect(contractReview().get).toHaveBeenLastCalledWith('t-1/versions', { signal: undefined })
  })

  it('resolveRevision 的 reason 默认空串（reject 允许不写理由）', async () => {
    await api.resolveRevision('t-1', 'r-1', 'reject')
    const [, opts] = lastPost()
    expect(opts.json).toEqual({ action: 'reject', reason: '' })
  })

  it('resolveRevision 显式 reason 透传', async () => {
    await api.resolveRevision('t-1', 'r-1', 'reject', '与合同第 3 条冲突')
    const [, opts] = lastPost()
    expect(opts.json).toEqual({ action: 'reject', reason: '与合同第 3 条冲突' })
  })
})

describe('contract-review api：上传与触发', () => {
  it('uploadContract 不带 modelName 时 formdata 里没有该字段', async () => {
    const file = new File(['x'], 'a.docx')
    await api.uploadContract(file)
    const [path, opts] = lastPost()
    expect(path).toBe('upload')
    const body = opts.body as FormData
    expect(body.get('file')).toBeInstanceOf(File)
    // 空串会让后端当成「用户指定了空模型」而不是「用默认模型」
    expect(body.has('model_name')).toBe(false)
    // 上传类超时：ky 默认 10s 会误杀大附件
    expect(opts.timeout).toBe(120_000)
  })

  it('uploadContract 给了 modelName 才 append', async () => {
    const file = new File(['x'], 'a.docx')
    await api.uploadContract(file, 'claude-opus')
    const body = lastPost()[1].body as FormData
    expect(body.get('model_name')).toBe('claude-opus')
  })

  it('confirmParty 打 confirm-party 且 body 原样透传（未给的可选字段不出现）', async () => {
    await api.confirmParty('t-1', { represented_party: 'party_a', client_note: '对方要求分期' })
    const [path, opts] = lastPost()
    expect(path).toBe('t-1/confirm-party')
    expect(opts.json).toEqual({ represented_party: 'party_a', client_note: '对方要求分期' })
  })
})

describe('contract-review api：划词直改三个端点不能混', () => {
  it('suggestDirectEdit 走 direct-edit/suggest（零副作用，可反复换个说法再生成）', async () => {
    await api.suggestDirectEdit({ contract_id: 11, subpath: 'a.docx', selection: '原文', instruction: '更客气' })
    const [path, opts] = lastPost()
    expect(path).toBe('direct-edit/suggest')
    // 归属靠 contract_id，不带 task_id：这是「无审查任务」的直改通道
    expect(opts.json).toEqual({ contract_id: 11, subpath: 'a.docx', selection: '原文', instruction: '更客气' })
  })

  it('applyDirectEdit 走 direct-edit/apply，归属是 case_id 时也原样透传', async () => {
    await api.applyDirectEdit({ case_id: 22, subpath: 'sub/b.docx', selection: '原文', suggested: '改后' })
    const [path, opts] = lastPost()
    expect(path).toBe('direct-edit/apply')
    expect(opts.json).toEqual({ case_id: 22, subpath: 'sub/b.docx', selection: '原文', suggested: '改后' })
  })

  it('applyTaskEdit 走 direct-edit/task/apply，归属是 task_id（不是 contract_id）', async () => {
    await api.applyTaskEdit({ task_id: 't-9', selection: '原文', suggested: '改后' })
    const [path, opts] = lastPost()
    // 三个端点共用后端落痕实现，区别只在归属方式；路径串了会对着「文件夹里的
    // 文件」而不是「任务的产物」落修订，律师看到的文档根本不会变
    expect(path).toBe('direct-edit/task/apply')
    expect(opts.json).toEqual({ task_id: 't-9', selection: '原文', suggested: '改后' })
  })

  it('applyTaskEdit 的 task_id 在 body 里，不做 encode（编码后后端反而查不到任务）', async () => {
    await api.applyTaskEdit({ task_id: 'a/b c', selection: 's', suggested: 't' })
    expect(lastPost()[1].json).toEqual({ task_id: 'a/b c', selection: 's', suggested: 't' })
  })
})
