/**
 * 客户转交材料的**纯逻辑**（无 React，可单测）：
 * 扩展名/大小校验、并入列表去重、文件大小格式化。
 *
 * 常量与后端 ``CourtSMSDocumentIntakeService`` 对齐，前端先拦一道，省掉
 * 「整批上传完再被后端拒」的等待；后端仍是唯一权威（这里只是提前反馈）。
 */

/** 与后端 allowed_extensions 一致 */
export const MATERIAL_ACCEPT = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.bmp'

/** 与后端 _INTAKE_MAX_SIZE_BYTES（50MB）一致 */
export const MATERIAL_MAX_BYTES = 50 * 1024 * 1024

const ACCEPT_EXTS = MATERIAL_ACCEPT.split(',').map((s) => s.trim().toLowerCase())

/** 单个文件是否可入库（扩展名 + 大小）；可入库返回 null */
export function rejectionReason(file: File): string | null {
  const lower = file.name.toLowerCase()
  if (!ACCEPT_EXTS.some((ext) => lower.endsWith(ext))) return '格式不支持'
  if (file.size > MATERIAL_MAX_BYTES) return '超过 50MB'
  return null
}

/**
 * 把新选的文件并入已有列表：按「名称+大小+修改时间」去重。
 *
 * 微信转来的材料重复拖入/重复选择是常态；同名不同内容（例如两次扫描）应视为
 * 不同文件，所以用不读内容的三元组判同——大 PDF 读内容会卡主线程。
 */
export function mergeFiles(
  prev: File[],
  incoming: File[],
): { next: File[]; rejected: { name: string; reason: string }[] } {
  const rejected: { name: string; reason: string }[] = []
  const seen = new Set(prev.map((f) => `${f.name}|${f.size}|${f.lastModified}`))
  const next = [...prev]

  for (const file of incoming) {
    const reason = rejectionReason(file)
    if (reason) {
      rejected.push({ name: file.name, reason })
      continue
    }
    const key = `${file.name}|${file.size}|${file.lastModified}`
    if (seen.has(key)) continue
    seen.add(key)
    next.push(file)
  }
  return { next, rejected }
}

/** 人读的文件大小 */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
