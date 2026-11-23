/**
 * `rewrite_folder_file` 的识别与信号收窄（node 单测，不涉 DOM）。
 *
 * 要锁住的事实：
 * 1. **命名空间后缀识别**：后端工具名带 `mcp__fachuan__` 前缀时仍认得出；
 * 2. **缺 `tool_call_id` 不认**：渐进到达的帧可能没带 id，按 id 覆盖缓存的调用方
 *    若拿到空键，会把这次改写的参数写进别人的账；
 * 3. **结果非字符串/失败/非改写工具一律 null**：宁可不刷新画布，也不能误刷新。
 */

import { describe, expect, it } from 'vitest'

import { fileRewriteSignalOf, rewriteCallOf } from './tool-rewrite'

const args = {
  subpath: '1-律师资料/1-合同/借款合同.docx',
  original: '逾期付款的，按日万分之五计息。',
  replacement: '逾期付款的，按日万分之三计息。',
}

describe('rewriteCallOf（认工具 + 解析参数）', () => {
  it('命名空间后缀也算 rewrite_folder_file，顺带取到显示文件名', () => {
    expect(rewriteCallOf({ name: 'mcp__fachuan__rewrite_folder_file', tool_call_id: 'r1', arguments: args })).toEqual({
      toolCallId: 'r1',
      args: {
        original: args.original,
        replacement: args.replacement,
        filename: '借款合同.docx',
      },
    })
    // 无前缀的裸名同样认
    expect(rewriteCallOf({ name: 'rewrite_folder_file', tool_call_id: 'r2', arguments: args })?.toolCallId).toBe('r2')
  })

  it('缺 tool_call_id：即便工具名与参数都对也不认', () => {
    expect(rewriteCallOf({ name: 'mcp__fachuan__rewrite_folder_file', arguments: args })).toBeNull()
  })

  it('参数是 JSON 字符串也解析；非改写工具名直接 null', () => {
    expect(
      rewriteCallOf({ name: 'rewrite_folder_file', tool_call_id: 'r3', arguments: JSON.stringify(args) })?.args.original,
    ).toBe(args.original)
    expect(rewriteCallOf({ name: 'read_folder_file', tool_call_id: 'r4', arguments: args })).toBeNull()
  })

  it('参数缺原文或改写全文时返回 null（空改写不得当成一次改写调用）', () => {
    expect(
      rewriteCallOf({ name: 'rewrite_folder_file', tool_call_id: 'r5', arguments: { original: args.original } }),
    ).toBeNull()
  })
})

describe('fileRewriteSignalOf（tool_result → 画布广播信号）', () => {
  it('成功结果 + 同次调用参数 → 带原文/改写全文的信号', () => {
    const signal = fileRewriteSignalOf(
      {
        name: 'mcp__fachuan__rewrite_folder_file',
        result: JSON.stringify({ applied: true, contract_id: 7, subpath: args.subpath, name: '借款合同.docx' }),
      },
      { original: args.original, replacement: args.replacement },
    )
    expect(signal).toMatchObject({
      kind: 'contract',
      ownerId: 7,
      subpath: args.subpath,
      original: args.original,
      replacement: args.replacement,
    })
  })

  it('is_error 或非字符串 result：不产生信号（不误刷新正在编辑的画布）', () => {
    const result = JSON.stringify({ applied: true, contract_id: 7, subpath: args.subpath })
    expect(fileRewriteSignalOf({ name: 'rewrite_folder_file', result, is_error: true })).toBeNull()
    // 对象 result 不能 String() 成 '[object Object]' 再当正文
    expect(fileRewriteSignalOf({ name: 'rewrite_folder_file', result: { applied: true } })).toBeNull()
  })
})
