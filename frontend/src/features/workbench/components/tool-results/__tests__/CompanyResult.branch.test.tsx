import { render, screen } from '@testing-library/react'
import { CompanyResult } from '../CompanyResult'

describe('CompanyResult - branch coverage', () => {
  // Branch: search_companies with >5 items (line 23-24)
  it('renders "...还有 N 家" when search results exceed 5', () => {
    const output = {
      results: Array.from({ length: 8 }, (_, i) => ({
        name: `Company ${i}`,
        status: '存续',
      })),
    }
    render(<CompanyResult input={{}} toolName="search_companies" output={output} />)
    expect(screen.getByText(/还有 3 家/)).toBeInTheDocument()
  })

  // Branch: search_companies with exactly 5 items (no extra text)
  it('does not show overflow text when exactly 5 results', () => {
    const output = {
      results: Array.from({ length: 5 }, (_, i) => ({
        name: `Company ${i}`,
      })),
    }
    render(<CompanyResult input={{}} toolName="search_companies" output={output} />)
    expect(screen.queryByText(/还有/)).not.toBeInTheDocument()
  })

  // Branch: get_company_profile with all optional fields present
  it('renders all optional fields in company profile', () => {
    const output = {
      name: 'Full Corp',
      status: '存续',
      legal_person: 'Zhang San',
      registered_capital: '5000万',
      establishment_date: '2010-01-01',
      industry: 'Technology',
      address: '123 Main St',
      risk_summary: 'No risks found',
    }
    render(<CompanyResult input={{}} toolName="get_company_profile" output={output} />)
    expect(screen.getByText('Full Corp')).toBeInTheDocument()
    expect(screen.getByText('Zhang San')).toBeInTheDocument()
    expect(screen.getByText('5000万')).toBeInTheDocument()
    expect(screen.getByText('2010-01-01')).toBeInTheDocument()
    expect(screen.getByText('Technology')).toBeInTheDocument()
    expect(screen.getByText('123 Main St')).toBeInTheDocument()
    expect(screen.getByText('No risks found')).toBeInTheDocument()
  })

  // Branch: status not in 存续/在业/开业 => secondary badge
  it('renders secondary badge for inactive status', () => {
    const output = {
      name: 'Deregistered Corp',
      status: '注销',
    }
    render(<CompanyResult input={{}} toolName="get_company_profile" output={output} />)
    expect(screen.getByText('注销')).toBeInTheDocument()
  })

  // Branch: status from operating_status fallback
  it('uses operating_status when status is missing', () => {
    const output = {
      name: 'Corp',
      operating_status: '在业',
    }
    render(<CompanyResult input={{}} toolName="get_company_profile" output={output} />)
    expect(screen.getByText('在业')).toBeInTheDocument()
  })

  // Branch: company_name fallback when name missing
  it('uses company_name when name is missing', () => {
    const output = {
      company_name: 'Fallback Corp',
      status: '存续',
    }
    render(<CompanyResult input={{}} toolName="get_company_profile" output={output} />)
    expect(screen.getByText('Fallback Corp')).toBeInTheDocument()
  })

  // Branch: no status at all => null badge
  it('renders profile without status (no badge)', () => {
    const output = { name: 'No Status Corp' }
    render(<CompanyResult input={{}} toolName="get_company_profile" output={output} />)
    expect(screen.getByText('No Status Corp')).toBeInTheDocument()
  })

  // Branch: get_company_personnel (line 36-38)
  it('renders personnel list', () => {
    const output = [{ name: 'Person A', role: 'Director' }]
    render(<CompanyResult input={{}} toolName="get_company_personnel" output={output} />)
    expect(screen.getByText('主要人员 (1)')).toBeInTheDocument()
    expect(screen.getByText('Person A')).toBeInTheDocument()
  })

  // Branch: null nameKey fallback in SimpleList
  it('renders SimpleList with empty nameKey value', () => {
    const output = [{ title: 'Title A' }]
    render(<CompanyResult input={{}} toolName="search_bidding_info" output={output} />)
    expect(screen.getByText('Title A')).toBeInTheDocument()
  })

  // Branch: RiskList with risk_type fallback and >5 items
  it('renders risk list with risk_type fallback and overflow', () => {
    const output = Array.from({ length: 7 }, (_, i) => ({
      risk_type: `Risk ${i}`,
      risk_level: '中',
    }))
    render(<CompanyResult input={{}} toolName="get_company_risks" output={output} />)
    expect(screen.getByText(/还有 2 条/)).toBeInTheDocument()
  })

  // Branch: RiskList item with content fallback
  it('renders risk item using content field', () => {
    const output = [{ content: 'Risk content here' }]
    render(<CompanyResult input={{}} toolName="get_company_risks" output={output} />)
    expect(screen.getByText('Risk content here')).toBeInTheDocument()
  })

  // Branch: CompactCompany with legal_person
  it('renders compact company with legal_person', () => {
    const output = {
      results: [{ name: 'Corp', legal_person: 'Li Si', status: '存续' }],
    }
    render(<CompanyResult input={{}} toolName="search_companies" output={output} />)
    expect(screen.getByText('Li Si')).toBeInTheDocument()
  })

  // Branch: CompactCompany without legal_person and without status
  it('renders compact company without optional fields', () => {
    const output = {
      results: [{ company_name: 'Bare Corp' }],
    }
    render(<CompanyResult input={{}} toolName="search_companies" output={output} />)
    expect(screen.getByText('Bare Corp')).toBeInTheDocument()
  })

  // Branch: extractList with data key
  it('extracts list from data key', () => {
    const output = { data: [{ name: 'A' }, { name: 'B' }] }
    render(<CompanyResult input={{}} toolName="get_company_shareholders" output={output} />)
    expect(screen.getByText('股东 (2)')).toBeInTheDocument()
  })

  // Branch: extractList with items key
  it('extracts list from items key', () => {
    const output = { items: [{ name: 'X' }] }
    render(<CompanyResult input={{}} toolName="get_company_shareholders" output={output} />)
    expect(screen.getByText('股东 (1)')).toBeInTheDocument()
  })

  // Branch: extractList with list key
  it('extracts list from list key', () => {
    const output = { list: [{ name: 'Y' }] }
    render(<CompanyResult input={{}} toolName="get_company_shareholders" output={output} />)
    expect(screen.getByText('股东 (1)')).toBeInTheDocument()
  })

  // Branch: extractList with non-array, non-object => empty
  it('returns empty for non-object output in search', () => {
    render(<CompanyResult input={{}} toolName="search_companies" output="invalid" />)
    expect(screen.getByText('未找到企业')).toBeInTheDocument()
  })

  // Branch: extractList with null output
  it('returns empty for null output', () => {
    render(<CompanyResult input={{}} toolName="get_company_shareholders" output={null} />)
    expect(screen.getByText(/暂无股东信息/)).toBeInTheDocument()
  })

  // Branch: unknown toolName returns null
  it('returns null for unknown tool', () => {
    const { container } = render(
      <CompanyResult input={{}} toolName="unknown_tool_xyz" output={{}} />,
    )
    expect(container.innerHTML).toBe('')
  })

  // Branch: SimpleList with role and ratio fields
  it('renders SimpleList with role and ratio', () => {
    const output = [{ name: 'Shareholder', role: '法人', ratio: '60%' }]
    render(<CompanyResult input={{}} toolName="get_company_shareholders" output={output} />)
    expect(screen.getByText('法人')).toBeInTheDocument()
    expect(screen.getByText('60%')).toBeInTheDocument()
  })

  // Branch: RiskList without risk_level
  it('renders risk item without risk_level', () => {
    const output = [{ title: 'No level risk' }]
    render(<CompanyResult input={{}} toolName="get_company_risks" output={output} />)
    expect(screen.getByText('No level risk')).toBeInTheDocument()
  })

  // Branch: search_companies with output as array directly
  it('renders search results from direct array output', () => {
    const output = [{ name: 'Direct Corp', status: '存续' }]
    render(<CompanyResult input={{}} toolName="search_companies" output={output} />)
    expect(screen.getByText('共 1 家企业')).toBeInTheDocument()
  })

  // Branch: CompactCompany with company_name fallback
  it('renders compact company with company_name fallback', () => {
    const output = {
      results: [{ company_name: 'Alt Name Corp' }],
    }
    render(<CompanyResult input={{}} toolName="search_companies" output={output} />)
    expect(screen.getByText('Alt Name Corp')).toBeInTheDocument()
  })

  // Branch: CompactCompany with empty status
  it('renders compact company with empty status string', () => {
    const output = {
      results: [{ name: 'Corp', status: '' }],
    }
    render(<CompanyResult input={{}} toolName="search_companies" output={output} />)
    expect(screen.getByText('Corp')).toBeInTheDocument()
  })

  // Branch: extractList with object but no recognizable array keys
  it('returns empty for object with no array keys', () => {
    render(
      <CompanyResult
        input={{}}
        toolName="search_companies"
        output={{ foo: 'bar', count: 5 }}
      />,
    )
    expect(screen.getByText('未找到企业')).toBeInTheDocument()
  })
})
