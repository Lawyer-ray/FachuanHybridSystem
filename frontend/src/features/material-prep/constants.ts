import type { InfoField, RecognitionPrefs } from './types'

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


/**
 * 上传体积上限 —— 必须与后端 `apps/message_hub/services/upload_policy.py` 同步。
 *
 * 前端先拦一道的理由不是「多一道保险」，而是**上传成本**：一份 1.2GB 的卷宗
 * 传满整条链路才被后端拒掉，用户白等几分钟还要吃掉一次上行带宽。
 * 这里直接按体积提前报错，文案与后端逐字一致，用户不会看到两种说法。
 *
 * ⚠️ 1GB 是业务决定（整卷客户材料），比 document_parsing 等工具型上传的
 *    50MB 宽得多。别拿这里的数字去反推其他上传口的口径。
 * ⚠️ 大文件耗时：上传超时看 lib/api 的 UPLOAD_TIMEOUT_MS；预览/OCR 不要
 *    假定文件已完全驻留内存（fetchAttachmentBytes 会缓存整份 bytes）。
 *
 * ⚠️ 改后端 `MANUAL_UPLOAD_MAX_SIZE_BYTES` / `MANUAL_UPLOAD_ARCHIVE_MAX_SIZE_BYTES`
 *    时必须同步改这里（前端无法 import Python 常量）。
 */
export const UPLOAD_MAX_SIZE_BYTES = 1024 * 1024 * 1024
/** 压缩包与单文件同额：整包上传时压缩包本身就是「一个文件」，
 *  再设一个更小的值只会制造「直传能过、打包反而被拒」的怪事 */
export const UPLOAD_ARCHIVE_MAX_SIZE_BYTES = 1024 * 1024 * 1024
/** 可展开的压缩包扩展名（与后端 ARCHIVE_EXTENSIONS 同口径） */
export const UPLOAD_ARCHIVE_EXTENSIONS = ['.zip', '.rar', '.7z'] as const

/** 单文件体积上限（压缩包放宽）；同时给 UI 文案用，避免两处各写一个数字 */
export function uploadSizeCapBytes(name: string): number {
  const lower = name.toLowerCase()
  return UPLOAD_ARCHIVE_EXTENSIONS.some((ext) => lower.endsWith(ext))
    ? UPLOAD_ARCHIVE_MAX_SIZE_BYTES
    : UPLOAD_MAX_SIZE_BYTES
}

/** 字节数 → 「65.7MB」/「1.0GB」这样的展示串（够用户核对量级） */
export function formatMB(bytes: number): string {
  const gb = bytes / (1024 * 1024 * 1024)
  if (gb >= 1) return `${gb.toFixed(1)}GB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

/** 桌面材料包列表的来源过滤：律师手动包 + 客户链接包（后端支持逗号分隔多值） */
export const PACK_SOURCE_TYPES = 'manual_upload,client_upload'

/** 「源下标 × 大数 + 页号」排序键的基数：段序按「源序 + 页序」比对时的合成键步长 */
export const MAT_PAGE_KEY_STRIDE = 1_000_000

/** 阅读器退场动画时长（对应 material-prep.css `.mp-reader.closing` 的 0.24s） */
export const READER_CLOSE_MS = 240
/** 卡片离场动画播完后移除 leaving 标记的等待（`.mp-packet.leave-*` 0.46s + 缓冲） */
export const PACK_LEAVE_REMOVAL_MS = 540

/**
 * **新建**材料包的默认识别选择（计费默认值，改动需产品确认）。
 *
 * 双引擎默认开启：交叉比对产出的分歧清单是律师发现 OCR 错字的唯一确定信号，
 * 默认关闭时多数包根本拿不到它（实测那个 164 页包是律师手动开的）。代价是同一份
 * PDF 付两次云端费用——所以设置菜单里明示计费、给一键关闭，且选择随包持久化。
 *
 * 版面策略仍默认 fast_text：电子页不上云、不计费。要不要让电子页也上云（更准但
 * 更慢更贵）由律师**按包**决定，不改全局默认。
 *
 * 存量草稿没有 recognition 键时不套用本默认（避免老包突然开始双倍计费），
 * 回到「仅文本层 + 自动容灾」——见 store 的 recognitionOf。
 *
 * 返回新对象：每次建草稿都拿自己的数组，避免多个包共享同一份可变选择集。
 */
export function defaultRecognition(): RecognitionPrefs {
  return {
    layoutMode: 'fast_text',
    engines: ['mineru', 'paddleocr_vl'],
    // 分段策略与判定都按包持久化：前者决定分段 LLM 调用次数，后者只在双引擎下有分歧可判。
    segmentStrategy: 'batch',
    judge: true,
  }
}
