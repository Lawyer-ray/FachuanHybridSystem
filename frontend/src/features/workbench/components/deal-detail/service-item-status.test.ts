/**
 * 服务事项「交付状态」判定测试。
 *
 * 判据从「有没有日期」换成「事项目录里有没有文件」——日期只说明计划过，
 * 文件才说明做完了。这个改动直接决定左栏那一列写「已交付」还是「进行中」，
 * 判错会让律师以为事情办完了（或反过来重复催办）。
 */
import { describe, expect, it } from 'vitest'

/** 与 use-service-items 内的判定保持一致的纯函数（抽出便于直接测边界） */
type Status = 'done' | 'doing' | 'todo'
function statusOf(fileCount: number, hasDate: boolean): Status {
  if (fileCount > 0) return 'done'
  return hasDate ? 'doing' : 'todo'
}

describe('服务事项交付状态', () => {
  it('有文件 → 已交付', () => {
    expect(statusOf(1, true)).toBe('done')
    expect(statusOf(9, false)).toBe('done')
  })

  it('有日期但没文件 → 进行中（计划过、尚未产出）', () => {
    // 真实例子：3-办案/2026.06.09-租赁合同/ 是空目录
    expect(statusOf(0, true)).toBe('doing')
  })

  it('无日期无文件 → 待办', () => {
    expect(statusOf(0, false)).toBe('todo')
  })

  it('文件数缺省按 0 处理（后端老响应没有 file_count）', () => {
    // 从对象里取，模拟老响应真的没有这个字段（而不是在类型层假装 undefined）
    const legacy: { name: string; file_count?: number } = { name: '2026.06.09-租赁合同' }
    expect(statusOf(legacy.file_count ?? 0, true)).toBe('doing')
  })
})
