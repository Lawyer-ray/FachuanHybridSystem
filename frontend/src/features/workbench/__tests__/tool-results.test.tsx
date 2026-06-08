import { renderToolResult } from '../components/tool-results/index'

vi.mock('../components/tool-results/CaseResult', () => ({
  CaseResult: () => <div data-testid="case-result">CaseResult</div>,
}))
vi.mock('../components/tool-results/CompanyResult', () => ({
  CompanyResult: () => <div data-testid="company-result">CompanyResult</div>,
}))
vi.mock('../components/tool-results/ContractResult', () => ({
  ContractResult: () => <div data-testid="contract-result">ContractResult</div>,
}))
vi.mock('../components/tool-results/ClientResult', () => ({
  ClientResult: () => <div data-testid="client-result">ClientResult</div>,
}))
vi.mock('../components/tool-results/ReminderResult', () => ({
  ReminderResult: () => <div data-testid="reminder-result">ReminderResult</div>,
}))
vi.mock('../components/tool-results/ListResult', () => ({
  ListResult: () => <div data-testid="list-result">ListResult</div>,
}))

const baseProps = { output: {}, input: {} }

describe('renderToolResult', () => {
  it('returns CaseResult for case-related tools', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'search_cases' })
    expect(result).toBeTruthy()
  })

  it('returns CompanyResult for company tools', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'search_company' })
    expect(result).toBeTruthy()
  })

  it('returns ContractResult for contract tools', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'list_contracts' })
    expect(result).toBeTruthy()
  })

  it('returns ClientResult for client tools', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'search_clients' })
    expect(result).toBeTruthy()
  })

  it('returns ReminderResult for reminder tools', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'list_reminders' })
    expect(result).toBeTruthy()
  })

  it('returns ListResult for list tools', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'list_lawyers' })
    expect(result).toBeTruthy()
  })

  it('returns null for unknown tool names', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'unknown_tool' })
    expect(result).toBeNull()
  })

  it('returns CaseResult for party tools', () => {
    const result = renderToolResult({ ...baseProps, toolName: 'add_party' })
    expect(result).toBeTruthy()
  })
})
