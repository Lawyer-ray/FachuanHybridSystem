import { render, screen } from '@testing-library/react'
import { CompanyResult } from '../CompanyResult'

describe('CompanyResult', () => {
  const baseProps = {
    input: {},
    toolName: 'search_companies',
  }

  it('renders "未找到企业" when search results are empty', () => {
    render(<CompanyResult {...baseProps} output={[]} />)
    expect(screen.getByText('未找到企业')).toBeInTheDocument()
  })

  it('renders company count for search results', () => {
    const output = {
      results: [
        { name: 'Company A', status: '存续' },
        { name: 'Company B', status: '在业' },
      ],
    }
    render(<CompanyResult {...baseProps} output={output} />)
    expect(screen.getByText('共 2 家企业')).toBeInTheDocument()
  })

  it('renders company profile for get_company_profile', () => {
    const output = {
      name: 'Test Corp',
      status: '存续',
      legal_person: 'John',
      registered_capital: '1000万',
      address: 'Beijing',
    }
    render(<CompanyResult input={{}} toolName="get_company_profile" output={output} />)
    expect(screen.getByText('Test Corp')).toBeInTheDocument()
    expect(screen.getByText('John')).toBeInTheDocument()
  })

  it('renders shareholders list', () => {
    const output = [{ name: 'Shareholder A', ratio: '30%' }, { name: 'Shareholder B', ratio: '70%' }]
    render(<CompanyResult input={{}} toolName="get_company_shareholders" output={output} />)
    expect(screen.getByText('股东 (2)')).toBeInTheDocument()
    expect(screen.getByText('Shareholder A')).toBeInTheDocument()
  })

  it('renders risk information', () => {
    const output = [{ title: 'Risk A', risk_level: '高' }]
    render(<CompanyResult input={{}} toolName="get_company_risks" output={output} />)
    expect(screen.getByText('Risk A')).toBeInTheDocument()
    expect(screen.getByText('高')).toBeInTheDocument()
  })

  it('renders empty shareholder info', () => {
    render(<CompanyResult input={{}} toolName="get_company_shareholders" output={[]} />)
    expect(screen.getByText(/暂无股东信息/)).toBeInTheDocument()
  })

  it('renders empty risk info', () => {
    render(<CompanyResult input={{}} toolName="get_company_risks" output={[]} />)
    expect(screen.getByText('暂无风险信息')).toBeInTheDocument()
  })

  it('renders compact company in search results', () => {
    const output = {
      results: [{ name: 'Company A', legal_person: 'John', status: '存续' }],
    }
    render(<CompanyResult {...baseProps} output={output} />)
    expect(screen.getByText('Company A')).toBeInTheDocument()
    expect(screen.getByText('存续')).toBeInTheDocument()
  })

  it('renders bidding info list', () => {
    const output = [{ title: 'Bidding A' }]
    render(<CompanyResult input={{}} toolName="search_bidding_info" output={output} />)
    expect(screen.getByText('招投标 (1)')).toBeInTheDocument()
  })
})
