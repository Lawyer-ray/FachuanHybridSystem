/**
 * `archiveSplitToCaseFolder` 的单测（node 环境，fetch 打桩）。
 *
 * 为什么这一组走**真实 ky 客户端 + fetch 桩**，而不是本目录既有用例的
 * `createApiClient` 桩：归档是会产生副作用的写接口（真的往案件卷宗目录里落文件），
 * 要连组包一起锁住——URL 前缀 + 资源路径、body 的 snake_case 字段名、以及
 * 「后端有缺省值的可选字段不传」。这些错了前端不报错，只会在后端 422 或静默落错地方。
 *
 * node 环境没有 document 基准，`new Request('/api/v1/…')` 会抛
 * 「Failed to parse URL」（ky 把 prefix 拼成相对地址后交给 `new Request`）。
 * 所以打一层 BaseRequest 把相对地址补成绝对地址，其余（ky 的 prefix 拼接、
 * JSON 序列化、超时、鉴权 hook）都跑真代码；断言只看 pathname，不看 origin。
 *
 * body 必须在 **fetch 那一刻**取：ky 在响应回来后会把原请求的 body 取消掉，
 * 事后 `req.clone().json()` 拿到的是 `TypeError: unusable`（实测）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { archiveSplitToCaseFolder } from './pdf-split'

const ORIGIN = 'http://localhost:8002'

/** 相对地址补基准 URL：node 的 Request 不接受相对路径，浏览器里由 document 兜底 */
class BaseRequest extends Request {
  constructor(input: string | URL | Request, init?: RequestInit) {
    super(typeof input === 'string' && input.startsWith('/') ? `${ORIGIN}${input}` : input, init)
  }
}

/** fetch 那一刻看到的请求（body 事后再读会是 unusable） */
interface SeenRequest {
  method: string
  pathname: string
  body: unknown
}

const seen: SeenRequest[] = []
const fetchMock = vi.fn()

/** 后端返回体（脱敏：案件名统一写「张某诉某公司买卖合同纠纷一案」） */
const PAYLOAD = {
  root: '/卷宗/张某诉某公司买卖合同纠纷一案',
  written: [{ filename: '001-起诉状.pdf', subdir: '01-立案材料', is_duplicate: false }],
  duplicates: [] as string[][],
  skipped: [{ doc_type: '未识别材料', reason: '类型未识别' }],
  notice_path: '/卷宗/张某诉某公司买卖合同纠纷一案/归档说明.md',
}

const SEGMENTS = [
  { page_start: 1, page_end: 3, doc_type: '起诉状', material_type: '起诉状' },
  { page_start: 4, page_end: 9, doc_type: '证据目录', material_type: '证据目录' },
]

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

/** 装一次 fetch：记录 method/pathname/body，返回给定响应 */
function stubFetch(response: Response = jsonResponse(PAYLOAD)) {
  fetchMock.mockImplementationOnce(async (req: Request) => {
    seen.push({
      method: req.method,
      pathname: new URL(req.url).pathname,
      body: await req.clone().json(),
    })
    return response
  })
}

beforeEach(() => {
  // node 环境没有可用的 localStorage：ky 的 beforeRequest 鉴权 hook 会读它取 token
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() })
  vi.stubGlobal('Request', BaseRequest)
  seen.length = 0
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('archiveSplitToCaseFolder：归案后归档到案件文件夹', () => {
  it('POST 到 /pdf-splitting/jobs/{jobId}/archive-to-case-folder，body 带 case_id 与段入参', async () => {
    stubFetch()

    await expect(archiveSplitToCaseFolder('job-7', 42, SEGMENTS)).resolves.toEqual(PAYLOAD)

    expect(seen).toEqual([
      {
        method: 'POST',
        pathname: '/api/v1/pdf-splitting/jobs/job-7/archive-to-case-folder',
        body: { case_id: 42, segments: SEGMENTS },
      },
    ])
  })

  it('date / write_duplicates 传了才进 body（后端对缺省值有自己的口径）', async () => {
    stubFetch()

    await archiveSplitToCaseFolder('job-7', 42, SEGMENTS, {
      date: '2026-01-02',
      writeDuplicates: true,
    })

    expect(seen[0]!.body).toEqual({
      case_id: 42,
      segments: SEGMENTS,
      date: '2026-01-02',
      write_duplicates: true,
    })
  })

  it('后端非 2xx 直接抛：归档失败由调用方决定只提示，不能吞成「成功」', async () => {
    stubFetch(jsonResponse({ detail: '案件不存在' }, 404))

    await expect(archiveSplitToCaseFolder('job-7', 42, SEGMENTS)).rejects.toThrow()
  })
})
