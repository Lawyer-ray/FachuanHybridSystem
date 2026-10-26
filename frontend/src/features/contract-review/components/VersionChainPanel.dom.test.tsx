// @vitest-environment jsdom
/**
 * VersionChainPanel 测试（jsdom）。
 *
 * 版本链解决的是「律师靠文件名猜改过几轮」：`[修订版]V1_日期` 改名就断链，
 * 排序只对同一天有效。面板必须把「第几版 / 谁改的 / 来源」讲清楚，并在没有
 * 记录时给出可执行的解释（而不是空白）。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { VersionChainButton, VersionChainPanel } from './VersionChainPanel'
import type { DocumentVersion } from '../types'

function v(over: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    id: 'v1',
    version_no: 1,
    kind: 'original',
    kind_label: '客户来稿',
    file_name: '施工合同.docx',
    file_path: 'uploads/a.docx',
    author: '客户',
    note: '',
    parent_id: null,
    created_at: '2026-10-25T00:00:00Z',
    ...over,
  }
}

describe('VersionChainPanel', () => {
  it('加载中给出提示', () => {
    render(<VersionChainPanel items={[]} isLoading error={null} />)
    expect(screen.getByText(/加载版本链/)).toBeTruthy()
  })

  it('错误时展示错误文案', () => {
    render(<VersionChainPanel items={[]} isLoading={false} error="请求失败" />)
    expect(screen.getByText('请求失败')).toBeTruthy()
  })

  it('空链给出可执行的说明（不是空白）', () => {
    render(<VersionChainPanel items={[]} isLoading={false} error={null} />)
    expect(screen.getByText(/还没有版本记录/)).toBeTruthy()
    // 告诉律师什么样会多出一个版本
    expect(screen.getByText(/律师编辑版/)).toBeTruthy()
  })

  it('按序号展示版本、来源与作者', () => {
    render(
      <VersionChainPanel
        isLoading={false}
        error={null}
        items={[
          v(),
          v({
            id: 'v2',
            version_no: 2,
            kind: 'ai',
            kind_label: 'AI 修订版',
            file_name: '施工合同[修订版]V1_20261025.docx',
            author: '法穿SI',
            parent_id: 'v1',
            note: 'AI 审查产物',
          }),
          v({
            id: 'v3',
            version_no: 3,
            kind: 'lawyer',
            kind_label: '律师编辑版',
            file_name: '施工合同[修订版]V1_20261025-律编v1.docx',
            author: '黄崧',
            parent_id: 'v2',
          }),
        ]}
      />,
    )
    expect(screen.getByText('V1')).toBeTruthy()
    expect(screen.getByText('V2')).toBeTruthy()
    expect(screen.getByText('V3')).toBeTruthy()
    expect(screen.getByText('客户来稿')).toBeTruthy()
    expect(screen.getByText('AI 修订版')).toBeTruthy()
    expect(screen.getByText('律师编辑版')).toBeTruthy()
    expect(screen.getByText('法穿SI')).toBeTruthy()
    expect(screen.getByText('黄崧')).toBeTruthy()
    expect(screen.getByText('AI 审查产物')).toBeTruthy()
  })

  it('文件被清理时仍展示节点（链不能断）', () => {
    render(
      <VersionChainPanel items={[v({ file_name: '', file_path: '' })]} isLoading={false} error={null} />,
    )
    expect(screen.getByText('（文件已清理）')).toBeTruthy()
    expect(screen.getByText('V1')).toBeTruthy()
  })
})

describe('VersionChainButton', () => {
  it('有版本时显示计数', () => {
    render(<VersionChainButton count={3} onClick={() => {}} />)
    expect(screen.getByText('版本链 · 3')).toBeTruthy()
  })

  it('无版本时不显示 0', () => {
    render(<VersionChainButton count={0} onClick={() => {}} />)
    expect(screen.getByText('版本链')).toBeTruthy()
  })
})
