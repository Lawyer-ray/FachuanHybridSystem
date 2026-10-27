import { createApiClient, UPLOAD_TIMEOUT_MS } from '@/lib/api'
import type { components } from '@/types/api-schema'

import type {
  CaseFolderBindingInfo,
  CaseListItem,
  ContractListItem,
  ContractPageResponse,
  FolderEntries,
  LawyerListItem,
  ReminderOut,
} from './types'

/**
 * 办案主页数据源：合同 + 律师列表接口只读拉取（slim 模式剔除归档材料清单，
 * 约减 60% 响应体积）；案件按合同 ID 按需加载。
 * 均返回裸数组、无业务 success 包装（见 types.ts 头注释的契约说明）。
 */
const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })
const casesApi = createApiClient({ prefix: '/api/v1/cases' })
const organizationApi = createApiClient({ prefix: '/api/v1/organization' })
const remindersApi = createApiClient({ prefix: '/api/v1/reminders' })

/** 分页拉取合同（服务端分页 + facets 全库计数；搜索/筛选随行，排序后端固定 id 倒序） */
export async function listContractsPage(opts: {
  page: number
  pageSize?: number
  status?: string
  cat?: string
  fee?: string
  q?: string
  /** 是否要 facets 计数（默认 true）。翻页时传 false：facets 是全库口径，
   *  与页码无关，逐页重算是 4 次白扫全表。 */
  includeFacets?: boolean
}): Promise<ContractPageResponse> {
  return contractsApi
    .get('contracts', {
      searchParams: {
        slim: 'true',
        page: String(opts.page),
        page_size: String(opts.pageSize ?? 50),
        ...(opts.status ? { status: opts.status } : {}),
        ...(opts.cat ? { case_type: opts.cat } : {}),
        ...(opts.fee ? { fee_mode: opts.fee } : {}),
        ...(opts.q ? { search: opts.q } : {}),
        ...(opts.includeFacets === false ? { include_facets: 'false' } : {}),
      },
    })
    .json<ContractPageResponse>()
}

export async function listCasesByContract(contractId: number): Promise<CaseListItem[]> {
  return casesApi
    .get('cases', { searchParams: { contract_id: String(contractId) } })
    .json<CaseListItem[]>()
}

/**
 * 单份合同（详情页直达 /projects/:id 时列表缓存不一定在）。端点返回全量 ContractOut，
 * 本页消费口径与列表行一致（representation_stages 运行时为中文标签数组、id 必有），
 * 多出的 finalized_materials 不消费，按 ContractListItem 投影即可复用 buildDeals。
 */
export async function getContract(contractId: number): Promise<ContractListItem> {
  return contractsApi.get('contracts/' + contractId).json<ContractListItem>()
}

/**
 * 某案件的直挂提醒（开庭等 hearing 类提醒挂在案件上）。/reminders/list 的
 * contract_id / case_id 都是「直挂」口径且互斥，合同直挂随 ContractOut.reminders、
 * 日志级随 CaseOut.logs[].reminders 下发，案件级只能按案逐个取。
 */
export async function listRemindersByCase(caseId: number): Promise<ReminderOut[]> {
  return remindersApi.get('list', { searchParams: { case_id: String(caseId) } }).json<ReminderOut[]>()
}

/**
 * 律师列表：slim=true 只取 id/real_name/phone/license_no/law_firm_name——
 * 本域只做「lawyer_id → 人名/电话/执业证/律所名」映射，不需要文件签 URL
 * 和律所嵌套对象（全量 500 人时那是 1000 次多余签名 + 嵌套 DTO 构建）。
 */
export async function listLawyers(): Promise<LawyerListItem[]> {
  return organizationApi.get('lawyers', { searchParams: { slim: 'true' } }).json<LawyerListItem[]>()
}

/* ============ 绑定文件夹（案件卡「文件夹视图」+ 右栏「合同文件夹」树共用） ============ */

export type FolderOwnerKind = 'case' | 'contract'

function folderApi(kind: FolderOwnerKind) {
  return kind === 'case' ? casesApi : contractsApi
}

/** 案件文件夹绑定（未绑定时端点返回 null；404 = 案件不存在/无权） */
export async function getCaseFolderBinding(caseId: number): Promise<CaseFolderBindingInfo | null> {
  return casesApi.get(String(caseId) + '/folder-binding').json<CaseFolderBindingInfo | null>()
}

/** 绑定文件夹某一层子项（subpath 为空 = 根；非递归、不含隐藏项） */
export async function listFolderEntries(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
): Promise<FolderEntries> {
  return folderApi(kind)
    .get(String(ownerId) + '/folder-entries', { searchParams: subpath ? { subpath } : {} })
    .json<FolderEntries>()
}

/** 在 subpath（空 = 绑定根）下新建子文件夹；重名/非法名由后端 400 拒 */
export async function createFolderEntry(kind: FolderOwnerKind, ownerId: number, subpath: string, name: string) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-mkdir', { json: { subpath, name } })
    .json<{ subpath: string; name: string }>()
}

/** 重命名 subpath 指向的文件/文件夹（name 为新名字） */
export async function renameFolderEntry(kind: FolderOwnerKind, ownerId: number, subpath: string, name: string) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-rename', { json: { subpath, name } })
    .json<{ subpath: string; name: string }>()
}

/** 拖拽 / 多文件上传到 subpath 目录（后端同名自动加序号，不覆盖既有文件） */
export async function uploadFolderFiles(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  files: File[],
) {
  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)
  return folderApi(kind)
    .post(String(ownerId) + '/folder-upload', {
      searchParams: subpath ? { subpath } : {},
      body: form,
      // 与其它模块上传端点同口径：ky 默认 10s，多文件扫描包必被误杀
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json<{ saved: Array<{ name: string; subpath: string }> }>()
}

/**
 * 原地保存（覆盖写）。
 *
 * 与 `uploadFolderFiles` 语义**相反**：上传是「不覆盖、同名加序号」，
 * 这里是明确的「覆盖这一份」。加序号就变成另存为，律师看到的还是旧内容。
 *
 * `expectMtime` 做乐观锁：两人同开时后保存的一方会拿到 409，前端提示
 * 「文件已被他人修改」，不静默丢掉前一个人的修改。
 */
export async function saveFolderFile(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  data: Blob,
  expectMtime?: number,
): Promise<{ subpath: string; name: string; size: number; modified_at?: string }> {
  const form = new FormData()
  form.append('file', data, fileNameOf(subpath))
  return folderApi(kind)
    .post(String(ownerId) + '/folder-save', {
      searchParams: {
        subpath,
        ...(expectMtime !== undefined ? { expect_mtime: String(expectMtime) } : {}),
      },
      body: form,
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json()
}

/** 另存为新文件（同目录、同名自动加序号、不动原文件） */
export async function saveFolderFileAs(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  name: string,
  data: Blob,
): Promise<{ subpath: string; name: string; size: number }> {
  const form = new FormData()
  form.append('file', data, name)
  return folderApi(kind)
    .post(String(ownerId) + '/folder-save-as', {
      searchParams: { subpath, name },
      body: form,
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json()
}

function fileNameOf(subpath: string): string {
  return subpath.split('/').pop() || 'document.docx'
}

/** 单文件预览直链（预览前经 withDownloadTicket 换一次性票据再 window.open） */
export function folderFileUrl(kind: FolderOwnerKind, ownerId: number, subpath: string): string {
  return (
    '/api/v1/' + (kind === 'case' ? 'cases' : 'contracts') + '/' + ownerId + '/folder-file?subpath=' + encodeURIComponent(subpath)
  )
}

/**
 * 登记「下一次保存另存为 name」的一次性意图（**不发文件字节**）。
 *
 * 为什么不是「取字节上传」：社区版 OnlyOffice 不暴露 `downloadAs`，编辑后的
 * 字节只存在于 DS 那边，浏览器拿不到。所以前端只能先把「另存为这个名字」的
 * 决定登记到编辑器会话上，再由 `requestSave()` 触发 DS forcesave，后端回调
 * 落盘时按意图写新文件、原文件不动。
 *
 * **只有合同文件夹有该端点**（cases 侧没有 folder-save-as-intent），调用方
 * 必须先按 `kind === 'contract'` 把关——这里不兜底成 no-op，否则「按钮点了没
 * 反应」这种假成功比 404 更难排查。
 *
 * `subpath` 传**已解码一次**的原文（与 `folderFileUrl` 同一口径）：后端回拼
 * source_path 时要按这个口径重新 quote，用来匹配两条编辑器会话。前端若多
 * encode 一次，后端就查不到会话，表现为「明明开着却报未打开」。
 *
 * 返回的 `name` 是后端清洗后的**实际**文件名（可能与入参不同），提示语用它。
 */
export async function registerFolderSaveAsIntent(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  name: string,
): Promise<{ registered: boolean; name: string; subpath: string }> {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-save-as-intent', { json: { subpath, name } })
    .json()
}

/** 复制文件/文件夹到目标目录（同名自动加序号，不覆盖） */
export async function copyFolderEntry(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  destSubpath: string,
) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-copy', { json: { subpath, dest_subpath: destSubpath } })
    .json<{ subpath: string; name: string }>()
}

/** 删除 = 移入绑定根下 _已删除/（带时间戳可恢复，非物理删除） */
export async function deleteFolderEntry(kind: FolderOwnerKind, ownerId: number, subpath: string) {
  return folderApi(kind)
    .post(String(ownerId) + '/folder-delete', { json: { subpath } })
    .json<{ subpath: string; name: string }>()
}

/* ============ 记收款：到账短信识别 + 发票拖拽（后端 contractpayment_enhance_api） ============ */

/** 到账短信解析草稿：识别不出的字段为空，由表单让人补 */
export interface PaymentParseDraft {
  amount: string | null
  received_at: string | null
  payer: string
  note: string
  hints: string[]
}

/** 发票（GET/POST 同一个投影）。payment_id 为 null = 先开票后付款，挂在合同名下待核销 */
export interface PaymentInvoice {
  id: number
  payment_id: number | null
  original_filename: string
  display_filename: string
  file_url: string
  invoice_code: string
  invoice_number: string
  invoice_date: string | null
  amount: string | null
  tax_amount: string | null
  total_amount: string | null
  seller_name: string
  buyer_name: string
  uploaded_at: string
}

/** 批量上传结果：成功逐张返回，失败逐张带原因 */
export interface InvoiceUploadResult {
  saved: PaymentInvoice[]
  failed: Array<{ filename: string; reason: string }>
  invoice_status: string
  invoice_status_label: string
  invoiced_amount: string
  duplicated_count: number
}

/** 粘贴的到账短信/截图文字 → 收款草稿（只解析，不落库） */
export async function parsePaymentText(text: string): Promise<PaymentParseDraft> {
  return contractsApi.post('finance/payments/parse-text', { json: { text } }).json<PaymentParseDraft>()
}

/** 某条收款下的发票列表（contract_id 参与行级鉴权，必须传） */
export async function listPaymentInvoices(paymentId: number, contractId: number): Promise<PaymentInvoice[]> {
  return contractsApi
    .get(`finance/payments/${paymentId}/invoices`, { searchParams: { contract_id: String(contractId) } })
    .json<PaymentInvoice[]>()
}

/**
 * 拖进来的发票：逐张识别 + 落盘 + 回填开票金额。
 *
 * 一次 multipart 传多张，后端逐张独立成败（一张坏文件不拖垮整批），
 * 所以错误处理在返回值里而不在 catch 里。
 */
export async function uploadPaymentInvoices(paymentId: number, files: File[]): Promise<InvoiceUploadResult> {
  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)
  return contractsApi
    .post(`finance/payments/${paymentId}/invoices`, { body: form, timeout: UPLOAD_TIMEOUT_MS })
    .json<InvoiceUploadResult>()
}

/** 删除发票（media 文件同删，开票金额由后端重算） */
export async function deletePaymentInvoice(invoiceId: number): Promise<{ success: boolean }> {
  return contractsApi.delete(`finance/invoices/${invoiceId}`).json<{ success: boolean }>()
}

/** 合同发票缓存 key（右栏待核销计数 / 记收款弹窗的池列表共用，上传/关联后按此失效） */
export const contractInvoiceKeys = {
  all: (contractId: number) => ['contract-invoices', contractId] as const,
  unlinked: (contractId: number) => ['contract-invoices', contractId, 'unlinked'] as const,
}

/** 合同发票列表：已核销 + 先开票挂合同的；unlinked 只看待核销 */
export async function listContractInvoices(contractId: number, unlinked = false): Promise<PaymentInvoice[]> {
  return contractsApi
    .get(`finance/contracts/${contractId}/invoices`, {
      searchParams: unlinked ? { unlinked: 'true' } : {},
    })
    .json<PaymentInvoice[]>()
}

/** 先开票后付款：票传到合同名下（不动开票金额），钱到账记完收款再 attach */
export async function uploadContractInvoices(contractId: number, files: File[]): Promise<InvoiceUploadResult> {
  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)
  return contractsApi
    .post(`finance/contracts/${contractId}/invoices`, { body: form, timeout: UPLOAD_TIMEOUT_MS })
    .json<InvoiceUploadResult>()
}

/** 把合同挂靠发票核销到一笔收款（返回该收款最新开票状态，就地刷新用） */
export async function attachPaymentInvoice(
  invoiceId: number,
  paymentId: number,
): Promise<{ invoice: PaymentInvoice; invoice_status: string; invoice_status_label: string; invoiced_amount: string }> {
  return contractsApi
    .post(`finance/invoices/${invoiceId}/attach`, { json: { payment_id: paymentId } })
    .json<{ invoice: PaymentInvoice; invoice_status: string; invoice_status_label: string; invoiced_amount: string }>()
}

/**
 * 复制**重命名后**的发票文件到系统剪贴板（后端 NSPasteboard 落板，同 Finder ⌘C）。
 *
 * 微信对话框直接 ⌘V 粘出文件本体。后端非 macOS / 无 pyobjc 时 success=false
 * 且 reason=unsupported，调用方降级复制文件名（口径同法院短信文书）。
 */
export async function copyInvoiceToClipboard(
  invoiceId: number,
): Promise<{ success: boolean; copied: number; reason: string | null }> {
  const res = await contractsApi
    .post(`finance/invoices/${invoiceId}/copy-to-clipboard`)
    .json<components['schemas']['InvoiceCopyOut'] & { message?: string }>()
  if (res.success === undefined && res.message) throw new Error(res.message)
  return { success: res.success === true, copied: Number(res.copied ?? 0), reason: res.reason ?? null }
}
