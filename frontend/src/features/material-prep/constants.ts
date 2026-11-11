import type { InfoField } from './types'

/** 人工归类的候选集（段头类型胶囊的选项） */
export const SEGMENT_TYPES = [
  '起诉状',
  '证据清单及明细',
  '财产保全资料',
  '双方当事人主体信息',
  '授权委托材料',
  '送达地址确认书',
  '诉讼费用退费账户确认书',
  '借条',
  '银行流水',
  '借款合同',
  '放款凭证',
  '利息计算表',
  '转账凭证',
  '聊天记录',
  '主体身份证明',
  '授权委托书',
  '送达回证',
  '送货单',
  '收货单',
  '发票',
  '证据材料',
  '未识别材料',
  '其他',
]

/** 段头色点取色盘 */
export const SEG_COLORS = ['#2563eb', '#22c55e', '#eab308', '#7c3aed', '#ef4444', '#0891b2'] as const

/** 字段库：右栏便签可选的字段 */
export const FIELD_LIB: InfoField[] = [
  { k: '委托人', v: '', src: '', srcRef: null, ph: '姓名或单位' },
  { k: '对方当事人', v: '', src: '', srcRef: null, ph: '姓名或单位', hint: '多个用、分隔' },
  { k: '受益人', v: '', src: '', srcRef: null, ph: '姓名或单位' },
  { k: '标的额', v: '', src: '', srcRef: null, ph: '如 120000' },
  { k: '关键日期', v: '', src: '', srcRef: null, ph: '如 2024-03-12' },
  { k: '事项 / 案由', v: '', src: '', srcRef: null, ph: '民间借贷 · 专项法律顾问' },
  { k: '业务类型', v: '', src: '', srcRef: null, opts: ['诉讼', '非诉', '常年顾问', '其他'] },
  { k: '管辖法院', v: '', src: '', srcRef: null, ph: '如 广州市天河区人民法院' },
  { k: '案号', v: '', src: '', srcRef: null, ph: '如 (2024)粤0101民初1001号' },
  { k: '备注', v: '', src: '', srcRef: null, ph: '随便写', ta: true },
]

export const MANUAL_SOURCE_TYPE = 'manual_upload'

/**
 * 上传体积上限 —— 必须与后端 `apps/message_hub/services/upload_policy.py` 同步。
 *
 * 前端先拦一道的理由不是「多一道保险」，而是**上传成本**：一份 65MB 的 PDF
 * 传满整条链路才被后端按 50MB 拒掉，用户白等几十秒还要吃掉一次上行带宽。
 * 这里直接按体积提前报错，文案与后端逐字一致，用户不会看到两种说法。
 *
 * ⚠️ 改后端 `MANUAL_UPLOAD_MAX_SIZE_BYTES` / `MANUAL_UPLOAD_ARCHIVE_MAX_SIZE_BYTES`
 *    时必须同步改这里（前端无法 import Python 常量）。
 */
export const UPLOAD_MAX_SIZE_BYTES = 50 * 1024 * 1024
/** 压缩包单独放宽：律所扫描件整包常见 100–200MB，后端展开侧自有硬上限兜底 */
export const UPLOAD_ARCHIVE_MAX_SIZE_BYTES = 200 * 1024 * 1024
/** 可展开的压缩包扩展名（与后端 ARCHIVE_EXTENSIONS 同口径） */
export const UPLOAD_ARCHIVE_EXTENSIONS = ['.zip', '.rar', '.7z'] as const

/** 单文件体积上限（压缩包放宽）；同时给 UI 文案用，避免两处各写一个数字 */
export function uploadSizeCapBytes(name: string): number {
  const lower = name.toLowerCase()
  return UPLOAD_ARCHIVE_EXTENSIONS.some((ext) => lower.endsWith(ext))
    ? UPLOAD_ARCHIVE_MAX_SIZE_BYTES
    : UPLOAD_MAX_SIZE_BYTES
}

/** 字节数 → 「65.7MB」这样的展示串（1 位小数，够用户核对） */
export function formatMB(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

/** 桌面材料包列表的来源过滤：律师手动包 + 客户链接包（后端支持逗号分隔多值） */
export const PACK_SOURCE_TYPES = 'manual_upload,client_upload'

/** 阅读器退场动画时长（对应 material-prep.css `.mp-reader.closing` 的 0.24s） */
export const READER_CLOSE_MS = 240
/** 卡片离场动画播完后移除 leaving 标记的等待（`.mp-packet.leave-*` 0.46s + 缓冲） */
export const PACK_LEAVE_REMOVAL_MS = 540
