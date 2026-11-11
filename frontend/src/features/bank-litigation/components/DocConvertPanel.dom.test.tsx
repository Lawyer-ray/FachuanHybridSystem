// @vitest-environment jsdom
/**
 * 要素式转换面板单测（jsdom）。
 *
 * 这一步的界面上有两处「会出错就白干」的地方，必须钉住：
 * - **文书类型默认值按案由自动匹配**，但律师能改；下拉框只列「起诉状」分类，
 *   该分类为空时才回落到全部分类。
 * - **转换会真的触发浏览器下载**：文件名必须是「要素式-<原名去扩展>.docx」，
 *   并且从 blob 生成 objectURL。命名错会让律师拿到一堆分不清的文件。
 *
 * mock 只打 ../api（转换 / 文书类型 / 历史记录）与 ../hooks/use-cases（案件详情），
 * 下载相关的 URL.createObjectURL / <a>.click 用探桩接住。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    listMbidTypes: vi.fn(),
    convertToElemental: vi.fn(),
    listConvertRecords: vi.fn(),
  }
})

vi.mock('../hooks/use-cases', () => ({ useCase: vi.fn() }))

import { convertToElemental, listConvertRecords, listMbidTypes } from '../api'
import { useCase } from '../hooks/use-cases'
import { DEMO_CONVERT_LOG, DEMO_CONVERT_MAPPING_DETAIL, DEMO_CONVERT_PREVIEW } from './demo-data'
import { DocConvertPanel } from './DocConvertPanel'

const listTypesMock = vi.mocked(listMbidTypes)
const convertMock = vi.mocked(convertToElemental)
const listRecordsMock = vi.mocked(listConvertRecords)
const useCaseMock = vi.mocked(useCase)

/** 默认的文书类型清单：起诉状分类里两个模板，另有一个非起诉状分类 */
function typesFixture() {
  return {
    categories: [
      {
        category: '起诉状',
        items: [
          { mbid: 'jrjkqsz', name: '金融借款起诉状' },
          { mbid: 'mjjdqsz', name: '民间借贷起诉状' },
        ],
      },
      {
        category: '答辩状',
        items: [{ mbid: 'dbs', name: '答辩状' }],
      },
    ],
  }
}

let createdUrls: Blob[]
let revokedUrls: string[]
let clickSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.clearAllMocks()
  createdUrls = []
  revokedUrls = []

  listTypesMock.mockResolvedValue(typesFixture() as never)
  listRecordsMock.mockResolvedValue({ items: [] } as never)
  useCaseMock.mockReturnValue({
    loading: false,
    error: null,
    data: { cause_of_action: '金融借款合同纠纷' },
    reload: vi.fn(),
  } as never)

  // 接住下载：真实现会往 document 挂 <a> 并 click，jsdom 下会报导航未实现
  vi.spyOn(URL, 'createObjectURL').mockImplementation((b: Blob | MediaSource) => {
    createdUrls.push(b as Blob)
    return `blob:mock/${createdUrls.length}`
  })
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation((u: string) => {
    revokedUrls.push(u)
  })
  clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
})

describe('DocConvertPanel · 文书类型加载', () => {
  it('loading 时显示加载态，不渲染转换区', () => {
    // 用永不 resolve 的 promise 让 hook 停在 loading
    listTypesMock.mockReturnValue(new Promise(() => {}) as never)
    render(<DocConvertPanel caseId={406} />)
    expect(screen.getByText('正在读取文书类型…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /转换并下载/ })).toBeNull()
  })

  it('error 时显示错误并可重试，重试成功后渲染转换区', async () => {
    listTypesMock.mockRejectedValueOnce(new Error('类型库 500'))
    render(<DocConvertPanel caseId={406} />)

    // useTypeList 在 catch 里已用 errMessage 把 Error 收成文案（'类型库 500'），
    // ErrorBlock 对已是字符串的值直接透传（只消一次毒，不再降级成 fallback），
    // 所以这里看到的是后端原话而不是 fallback「文书类型读取失败」。
    await waitFor(() => expect(screen.getByText('类型库 500')).toBeTruthy())
    listTypesMock.mockResolvedValue(typesFixture() as never)
    fireEvent.click(screen.getByRole('button', { name: '重新加载' }))
    await waitFor(() => expect(screen.getByLabelText('文书类型')).toBeTruthy())
  })

  it('下拉框只列「起诉状」分类的模板（答辩状不该出现在这里）', async () => {
    render(<DocConvertPanel caseId={406} />)
    const select = await screen.findByLabelText('文书类型')

    const options = [...select.querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toEqual(['金融借款起诉状（jrjkqsz）', '民间借贷起诉状（mjjdqsz）'])
    expect(screen.queryByText('答辩状（dbs）')).toBeNull()
  })

  it('没有「起诉状」分类时回落到全部分类（否则下拉框会是空的，无法转换）', async () => {
    listTypesMock.mockResolvedValue({
      categories: [{ category: '其他', items: [{ mbid: 'x', name: '某文书' }] }],
    } as never)
    render(<DocConvertPanel caseId={406} />)

    await waitFor(() => expect(screen.getByLabelText('文书类型')).toBeTruthy())
    expect(screen.getByText('某文书（x）')).toBeTruthy()
  })
})

describe('DocConvertPanel · 按案由自动匹配类型', () => {
  it('金融借款案由 → 默认选中 jrjkqsz，顶部统计格显示中文名', async () => {
    render(<DocConvertPanel caseId={406} />)
    const select = (await screen.findByLabelText('文书类型')) as HTMLSelectElement

    expect(select.value).toBe('jrjkqsz')
    // 顶部「文书类型」格显示的是 name 而不是 mbid
    expect(screen.getAllByText('金融借款起诉状').length).toBeGreaterThan(0)
  })

  it('民间借贷案由 → 默认选中 mjjdqsz', async () => {
    useCaseMock.mockReturnValue({
      loading: false,
      error: null,
      data: { cause_of_action: '民间借贷纠纷' },
      reload: vi.fn(),
    } as never)
    render(<DocConvertPanel caseId={406} />)
    const select = (await screen.findByLabelText('文书类型')) as HTMLSelectElement
    expect(select.value).toBe('mjjdqsz')
  })

  it('律师改下拉框能改掉默认值', async () => {
    render(<DocConvertPanel caseId={406} />)
    const select = (await screen.findByLabelText('文书类型')) as HTMLSelectElement

    fireEvent.change(select, { target: { value: 'mjjdqsz' } })
    expect(select.value).toBe('mjjdqsz')
  })
})

describe('DocConvertPanel · 转换与下载', () => {
  it('没选文件时「转换并下载」不可点，并提示先选文件', async () => {
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    expect((screen.getByRole('button', { name: /转换并下载/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('先选文件再转换')).toBeTruthy()
  })

  it('选文件后按钮可点，转换成功触发下载且文件名是「要素式-<原名去扩展>.docx」', async () => {
    const blob = new Blob(['docx-bytes'], { type: 'application/octet-stream' })
    convertMock.mockResolvedValue(blob as never)

    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'], '民事起诉状.docx', { type: 'application/msword' })
    fireEvent.change(input, { target: { files: [file] } })

    // 选中后按钮上显示文件名与大小
    expect(screen.getByText(/民事起诉状\.docx/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /转换并下载/ }))

    await waitFor(() => expect(convertMock).toHaveBeenCalledWith(file, 'jrjkqsz'))
    expect(createdUrls).toHaveLength(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)

    // 成功提示带文件名与大小
    await waitFor(() => expect(screen.getByText(/已生成并下载：要素式-民事起诉状\.docx/)).toBeTruthy())
  })

  it('pdf 源文件也去掉扩展名（不能出现「要素式-起诉状.pdf.docx」）', async () => {
    convertMock.mockResolvedValue(new Blob(['x']) as never)
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], '起诉状.PDF')] } })

    fireEvent.click(screen.getByRole('button', { name: /转换并下载/ }))
    await waitFor(() => expect(screen.getByText(/要素式-起诉状\.docx/)).toBeTruthy())
  })

  it('转换失败时显示后端原话，且不触发下载', async () => {
    convertMock.mockRejectedValue(new Error('ZNSZJ_ENABLED 未开启'))
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.docx')] } })
    fireEvent.click(screen.getByRole('button', { name: /转换并下载/ }))

    await waitFor(() => expect(screen.getByText('ZNSZJ_ENABLED 未开启')).toBeTruthy())
    expect(clickSpy).not.toHaveBeenCalled()
  })

  it('「清空」把已选文件与结果一起清掉，按钮回到禁用', async () => {
    convertMock.mockResolvedValue(new Blob(['x']) as never)
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.docx')] } })
    fireEvent.click(screen.getByRole('button', { name: '清空' }))

    expect(screen.getByText(/选择 \.docx \/ \.doc \/ \.pdf/)).toBeTruthy()
    expect((screen.getByRole('button', { name: /转换并下载/ }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('DocConvertPanel · 静态说明区', () => {
  it('转换内容表逐项列出，必填/选填分开标', async () => {
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    expect(
      screen.getByText(`传统字段 → 要素式栏位 · ${DEMO_CONVERT_MAPPING_DETAIL.length} 项`),
    ).toBeTruthy()
    for (const m of DEMO_CONVERT_MAPPING_DETAIL) {
      // 同一个字段名可能既是 from 又是另一项的 to（如「诉讼请求」），用 allBy
      expect(screen.getAllByText(m.from).length).toBeGreaterThan(0)
      expect(screen.getByText(`例：${m.sample}`)).toBeTruthy()
    }
    const required = DEMO_CONVERT_MAPPING_DETAIL.filter((m) => m.required).length
    expect(screen.getAllByText('必填')).toHaveLength(required)
    expect(screen.getAllByText('选填')).toHaveLength(DEMO_CONVERT_MAPPING_DETAIL.length - required)
  })

  it('转换前后对比：要素式侧标出「要素式新增」，传统侧标「原稿无此栏」', async () => {
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    const newFields = DEMO_CONVERT_PREVIEW.filter((p) => !p.matched).length
    expect(newFields).toBeGreaterThan(0)
    expect(screen.getAllByText('要素式新增')).toHaveLength(newFields)
    expect(screen.getAllByText('原稿无此栏')).toHaveLength(newFields)
  })

  it('明说「不改写事实表述」，新增栏留空待律师补填', async () => {
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')
    expect(screen.getByText(/不改写事实表述/)).toBeTruthy()
    expect(screen.getByText(/需律师补填后再递交/)).toBeTruthy()
  })

  it('后端开关 ZNSZJ_ENABLED 前置说明摆在页面上', async () => {
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')
    expect(screen.getByText('转换需要后端开启开关')).toBeTruthy()
    expect(screen.getByText('ZNSZJ_ENABLED')).toBeTruthy()
    expect(screen.getByText('未开启时接口返回 403')).toBeTruthy()
  })
})

describe('DocConvertPanel · 与转换记录联动', () => {
  it('记录数为 0 时顶部「转换次数」显示 0，接口有记录时数字更新', async () => {
    listRecordsMock.mockResolvedValue({ items: [{ id: 1 }, { id: 2 }] } as never)
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    // HistoryBlock 通过 onCount 回传条数；有记录时演示数据不接管
    await waitFor(() => {
      const cell = screen.getByText('转换次数').parentElement!
      expect(cell.textContent).toContain('2')
    })
  })

  it('后端无记录时铺演示记录，并标「样例数据」', async () => {
    render(<DocConvertPanel caseId={406} />)
    await screen.findByLabelText('文书类型')

    await waitFor(() =>
      expect(
        screen.getByText(`共 ${DEMO_CONVERT_LOG.length} 条 · 样例数据`),
      ).toBeTruthy(),
    )
  })
})
