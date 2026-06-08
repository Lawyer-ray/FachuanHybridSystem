/**
 * Organization Types Tests
 * 测试组织模块的标签映射完整性
 */

import { TEAM_TYPE_LABELS, ORGANIZATION_TAB_LABELS } from '../types'
import type { TeamType, OrganizationTab } from '../types'

const TEAM_TYPE_VALUES: TeamType[] = ['lawyer', 'biz']
const ORGANIZATION_TAB_VALUES: OrganizationTab[] = ['lawfirms', 'lawyers', 'teams', 'credentials']

describe('TEAM_TYPE_LABELS', () => {
  it('maps every TeamType to a non-empty string', () => {
    for (const val of TEAM_TYPE_VALUES) {
      expect(TEAM_TYPE_LABELS[val]).toBeTruthy()
      expect(typeof TEAM_TYPE_LABELS[val]).toBe('string')
    }
  })

  it('has 2 entries', () => {
    expect(Object.keys(TEAM_TYPE_LABELS)).toHaveLength(2)
  })

  it('uses Chinese labels', () => {
    expect(TEAM_TYPE_LABELS.lawyer).toBe('律师团队')
    expect(TEAM_TYPE_LABELS.biz).toBe('业务团队')
  })
})

describe('ORGANIZATION_TAB_LABELS', () => {
  it('maps every OrganizationTab to a non-empty string', () => {
    for (const val of ORGANIZATION_TAB_VALUES) {
      expect(ORGANIZATION_TAB_LABELS[val]).toBeTruthy()
      expect(typeof ORGANIZATION_TAB_LABELS[val]).toBe('string')
    }
  })

  it('has 4 entries', () => {
    expect(Object.keys(ORGANIZATION_TAB_LABELS)).toHaveLength(4)
  })

  it('uses Chinese labels', () => {
    expect(ORGANIZATION_TAB_LABELS.lawfirms).toBe('律所')
    expect(ORGANIZATION_TAB_LABELS.lawyers).toBe('律师')
    expect(ORGANIZATION_TAB_LABELS.teams).toBe('团队')
    expect(ORGANIZATION_TAB_LABELS.credentials).toBe('凭证')
  })
})
