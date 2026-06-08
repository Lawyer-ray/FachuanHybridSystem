import { render, screen } from '@testing-library/react'
import { ContractResult } from '../ContractResult'

vi.mock('@/lib/format', () => ({
  formatAmountInt: (n: number) => `${n}元`,
}))

describe('ContractResult', () => {
  const baseProps = {
    input: {},
    toolName: 'list_contracts',
  }

  it('renders "未找到合同" when output is empty', () => {
    render(<ContractResult {...baseProps} output={[]} />)
    expect(screen.getByText('未找到合同')).toBeInTheDocument()
  })

  it('renders contract count for list results', () => {
    const output = {
      results: [
        { title: 'Contract A', status: 'active' },
        { title: 'Contract B', status: 'expired' },
      ],
    }
    render(<ContractResult {...baseProps} output={output} />)
    expect(screen.getByText('共 2 份合同')).toBeInTheDocument()
  })

  it('renders single contract detail for get_contract', () => {
    const output = {
      title: 'Service Agreement',
      contract_number: 'SA-001',
      contract_type: '服务合同',
      status: 'active',
    }
    render(<ContractResult input={{}} toolName="get_contract" output={output} />)
    expect(screen.getByText('Service Agreement')).toBeInTheDocument()
    expect(screen.getByText('SA-001')).toBeInTheDocument()
    expect(screen.getByText('生效中')).toBeInTheDocument()
  })

  it('renders compact contract in list', () => {
    const output = {
      results: [{ title: 'Contract A', amount: 10000 }],
    }
    render(<ContractResult {...baseProps} output={output} />)
    expect(screen.getByText('Contract A')).toBeInTheDocument()
    expect(screen.getByText('10000元')).toBeInTheDocument()
  })

  it('shows "未命名合同" when name is missing', () => {
    render(<ContractResult input={{}} toolName="get_contract" output={{}} />)
    expect(screen.getByText('未命名合同')).toBeInTheDocument()
  })

  it('renders parties list', () => {
    const output = {
      title: 'Contract A',
      parties: [{ name: 'Party A' }, { name: 'Party B' }],
    }
    render(<ContractResult input={{}} toolName="get_contract" output={output} />)
    expect(screen.getByText('Party A、Party B')).toBeInTheDocument()
  })
})
