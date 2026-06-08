import { formatClientText } from '../utils/format-client-text'
import type { Client } from '../types'

function makeClient(overrides: Partial<Client> = {}): Client {
  return {
    id: 1,
    name: 'Test',
    is_our_client: true,
    phone: null,
    address: null,
    client_type: 'natural',
    client_type_label: '自然人',
    id_number: null,
    legal_representative: null,
    legal_representative_id_number: null,
    identity_docs: [],
    ...overrides,
  }
}

describe('formatClientText', () => {
  it('formats natural person with name only', () => {
    const result = formatClientText(makeClient({ name: 'Wang' }))
    expect(result).toBe('姓名：Wang')
  })

  it('detects male gender from id number', () => {
    const result = formatClientText(makeClient({
      name: 'Wang',
      id_number: '000000000000000010', // 17th digit 1 -> odd -> male
    }))
    expect(result).toContain('姓名：Wang，男')
    expect(result).toContain('身份证号：000000000000000010')
  })

  it('detects female gender from id number', () => {
    const result = formatClientText(makeClient({
      name: 'Li',
      client_type: 'natural',
      id_number: '000000000000000020', // 17th digit 2 -> even -> female
    }))
    expect(result).toContain('姓名：Li，女')
  })

  it('returns null gender for short id number', () => {
    const result = formatClientText(makeClient({
      name: 'Zhang',
      id_number: '12345',
    }))
    expect(result).toContain('姓名：Zhang')
    expect(result).not.toContain('男')
    expect(result).not.toContain('女')
  })

  it('formats legal entity with unified social credit code', () => {
    const result = formatClientText(makeClient({
      name: 'Company A',
      client_type: 'legal',
      id_number: '91110000MA12345678',
    }))
    expect(result).toContain('名称：Company A')
    expect(result).toContain('统一社会信用代码：91110000MA12345678')
  })

  it('includes phone and address', () => {
    const result = formatClientText(makeClient({
      name: 'Wang',
      phone: '00000000000',
      address: 'Beijing',
    }))
    expect(result).toContain('手机号：00000000000')
    expect(result).toContain('地址：Beijing')
  })

  it('shows legal_representative for legal entity', () => {
    const result = formatClientText(makeClient({
      name: 'Corp',
      client_type: 'legal',
      legal_representative: 'Wang',
    }))
    expect(result).toContain('法定代表人：Wang')
  })

  it('shows responsible person for non_legal_org', () => {
    const result = formatClientText(makeClient({
      name: 'Org',
      client_type: 'non_legal_org',
      legal_representative: 'Li',
    }))
    expect(result).toContain('负责人：Li')
  })

  it('does not show legal_representative for natural person', () => {
    const result = formatClientText(makeClient({
      name: 'Wang',
      client_type: 'natural',
      legal_representative: 'Li',
    }))
    expect(result).not.toContain('法定代表人')
    expect(result).not.toContain('负责人')
  })
})
