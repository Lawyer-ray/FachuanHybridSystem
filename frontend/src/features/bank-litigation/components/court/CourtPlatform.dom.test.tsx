// @vitest-environment jsdom
/**
 * CourtPlatform：法院平台信息 + 校验规则口径（递交前该读一遍的背景）。
 *
 * 这两块是「系统拦了但不说为什么」的解药：法院怎么联系、几个工作日内答复、
 * 三处校验各自在比什么、不一致是阻断还是只提示。所以逐项钉住：
 * - 六行平台信息逐行照实（电话/地址是占位值，隐私闸门要求）
 * - 须知按原顺序编号列出
 * - 每条校验规则写明比对项与「阻断 / 仅提示」的后果
 *
 * 数据全部来自 demo-data（纯展示组件，无 props、无网络）。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DEMO_COURT_CHECK_RULES, DEMO_COURT_PLATFORM } from '../demo-data'
import { CourtPlatform } from './CourtPlatform'

describe('CourtPlatform · 法院平台信息', () => {
  it('法院名称 / 立案窗口 / 电话 / 工作时间 / 网上立案 / 地址逐行照实', () => {
    render(<CourtPlatform />)
    const p = DEMO_COURT_PLATFORM
    expect(screen.getByText(p.courtName)).toBeTruthy()
    expect(screen.getByText(p.filingChamber)).toBeTruthy()
    expect(screen.getByText(p.phone)).toBeTruthy()
    expect(screen.getByText(p.workTime)).toBeTruthy()
    expect(screen.getByText(p.onlineChannel)).toBeTruthy()
    expect(screen.getByText(p.address)).toBeTruthy()
  })

  it('须知按原顺序编号列出，一条不漏', () => {
    render(<CourtPlatform />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(DEMO_COURT_PLATFORM.notices.length)
    DEMO_COURT_PLATFORM.notices.forEach((n, i) => {
      const li = items[i]!
      expect(li.textContent).toContain(n)
      expect(li.textContent?.startsWith(String(i + 1))).toBe(true)
    })
  })
})

describe('CourtPlatform · 校验规则口径', () => {
  it('每条规则写明标题、比对项与判定口径', () => {
    render(<CourtPlatform />)
    for (const r of DEMO_COURT_CHECK_RULES) {
      expect(screen.getByText(r.title)).toBeTruthy()
      expect(screen.getByText(`比对项：${r.fields}`)).toBeTruthy()
      expect(screen.getByText(r.rule)).toBeTruthy()
    }
  })

  it('不一致的后果按 onFail 分「阻断递交」与「仅提示」', () => {
    render(<CourtPlatform />)
    const block = DEMO_COURT_CHECK_RULES.filter((r) => r.onFail === 'block').length
    const warn = DEMO_COURT_CHECK_RULES.filter((r) => r.onFail === 'warn').length
    expect(block + warn).toBe(DEMO_COURT_CHECK_RULES.length)
    expect(screen.getAllByText('不一致则阻断递交')).toHaveLength(block)
    expect(screen.getAllByText('不一致仅提示')).toHaveLength(warn)
  })
})
