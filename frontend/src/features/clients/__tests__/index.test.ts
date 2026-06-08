/**
 * Client Feature Index Export Tests
 */

import { clientApi } from '../api'
import {
  CLIENT_TYPE_LABELS,
  DOC_TYPE_LABELS,
  CLUE_TYPE_LABELS,
  NATURAL_DOC_TYPES,
  LEGAL_DOC_TYPES,
} from '../types'

describe('clients feature index exports', () => {
  it('exports clientApi', () => {
    expect(clientApi).toBeDefined()
    expect(typeof clientApi.list).toBe('function')
    expect(typeof clientApi.get).toBe('function')
    expect(typeof clientApi.create).toBe('function')
    expect(typeof clientApi.update).toBe('function')
    expect(typeof clientApi.delete).toBe('function')
  })

  it('exports CLIENT_TYPE_LABELS', () => {
    expect(CLIENT_TYPE_LABELS).toBeDefined()
    expect(CLIENT_TYPE_LABELS.natural).toBe('自然人')
  })

  it('exports DOC_TYPE_LABELS', () => {
    expect(DOC_TYPE_LABELS).toBeDefined()
    expect(Object.keys(DOC_TYPE_LABELS).length).toBeGreaterThan(0)
  })

  it('exports CLUE_TYPE_LABELS', () => {
    expect(CLUE_TYPE_LABELS).toBeDefined()
    expect(CLUE_TYPE_LABELS.bank).toBe('银行账户')
  })

  it('exports NATURAL_DOC_TYPES and LEGAL_DOC_TYPES', () => {
    expect(NATURAL_DOC_TYPES).toBeDefined()
    expect(NATURAL_DOC_TYPES.length).toBeGreaterThan(0)
    expect(LEGAL_DOC_TYPES).toBeDefined()
    expect(LEGAL_DOC_TYPES.length).toBeGreaterThan(0)
  })

  it('clientApi default export is the same object', async () => {
    const { default: defaultApi } = await import('../api')
    expect(defaultApi).toBe(clientApi)
  })
})
