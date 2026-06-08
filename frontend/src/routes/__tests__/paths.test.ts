import { PATHS, generatePath } from '../paths'

describe('PATHS', () => {
  it('defines auth paths', () => {
    expect(PATHS.LOGIN).toBe('/login')
    expect(PATHS.REGISTER).toBe('/register')
    expect(PATHS.FORGOT_PASSWORD).toBe('/forgot-password')
    expect(PATHS.RESET_PASSWORD).toBe('/reset-password')
  })

  it('defines admin dashboard paths', () => {
    expect(PATHS.ADMIN_DASHBOARD).toBe('/admin/dashboard')
    expect(PATHS.ADMIN_INBOX).toBe('/admin/inbox')
    expect(PATHS.ADMIN_CASES).toBe('/admin/cases')
    expect(PATHS.ADMIN_CONTRACTS).toBe('/admin/contracts')
    expect(PATHS.ADMIN_CLIENTS).toBe('/admin/clients')
  })

  it('defines organization paths', () => {
    expect(PATHS.ADMIN_ORGANIZATION).toBe('/admin/organization')
    expect(PATHS.ADMIN_LAWFIRMS).toBe('/admin/organization/lawfirms')
    expect(PATHS.ADMIN_LAWYERS).toBe('/admin/organization/lawyers')
    expect(PATHS.ADMIN_TEAMS).toBe('/admin/organization/teams')
    expect(PATHS.ADMIN_CREDENTIALS).toBe('/admin/organization/credentials')
  })

  it('defines settings paths', () => {
    expect(PATHS.ADMIN_SETTINGS).toBe('/admin/settings')
    expect(PATHS.ADMIN_SETTINGS_LAW_FIRM).toBe('/admin/settings/law-firm')
    expect(PATHS.ADMIN_SETTINGS_TEAM).toBe('/admin/settings/team')
    expect(PATHS.ADMIN_SETTINGS_LAWYER).toBe('/admin/settings/lawyer')
    expect(PATHS.ADMIN_SETTINGS_CONFIG).toBe('/admin/settings/config/:category')
  })

  it('defines automation paths', () => {
    expect(PATHS.ADMIN_AUTOMATION).toBe('/admin/automation')
    expect(PATHS.ADMIN_AUTOMATION_QUOTES).toBe('/admin/automation/preservation-quotes')
    expect(PATHS.ADMIN_AUTOMATION_RECOGNITION).toBe('/admin/automation/document-recognition')
  })

  it('defines tools paths', () => {
    expect(PATHS.ADMIN_TOOLS_COURT_SMS).toBe('/admin/tools/court-sms')
    expect(PATHS.ADMIN_TOOLS_COURIER).toBe('/admin/tools/courier-tracking')
    expect(PATHS.ADMIN_TOOLS_ELEMENT).toBe('/admin/tools/element-convert')
    expect(PATHS.ADMIN_TOOLS_LPR).toBe('/admin/tools/lpr-calculator')
    expect(PATHS.ADMIN_TOOLS_CONTENT_OPS).toBe('/admin/tools/content-ops')
  })

  it('defines parameterized paths with colons', () => {
    expect(PATHS.ADMIN_INBOX_DETAIL).toContain(':id')
    expect(PATHS.ADMIN_CASE_DETAIL).toContain(':id')
    expect(PATHS.ADMIN_CLIENT_DETAIL).toContain(':id')
    expect(PATHS.ADMIN_CONTRACT_DETAIL).toContain(':id')
    expect(PATHS.ADMIN_CASE_EDIT).toContain(':id/edit')
  })

  it('defines external links', () => {
    expect(PATHS.GITHUB).toMatch(/^https:\/\//)
  })
})

describe('generatePath', () => {
  it('generates inbox detail path', () => {
    expect(generatePath.inboxDetail('123')).toBe('/admin/inbox/123')
    expect(generatePath.inboxDetail(456)).toBe('/admin/inbox/456')
  })

  it('generates case detail and edit paths', () => {
    expect(generatePath.caseDetail('abc')).toBe('/admin/cases/abc')
    expect(generatePath.caseEdit('abc')).toBe('/admin/cases/abc/edit')
  })

  it('generates contract detail and edit paths', () => {
    expect(generatePath.contractDetail('1')).toBe('/admin/contracts/1')
    expect(generatePath.contractEdit(2)).toBe('/admin/contracts/2/edit')
  })

  it('generates client detail and edit paths', () => {
    expect(generatePath.clientDetail('10')).toBe('/admin/clients/10')
    expect(generatePath.clientEdit(20)).toBe('/admin/clients/20/edit')
  })

  it('generates law firm paths', () => {
    expect(generatePath.lawFirmDetail('5')).toBe('/admin/organization/lawfirms/5')
    expect(generatePath.lawFirmEdit(5)).toBe('/admin/organization/lawfirms/5/edit')
  })

  it('generates lawyer paths', () => {
    expect(generatePath.lawyerDetail('3')).toBe('/admin/organization/lawyers/3')
    expect(generatePath.lawyerEdit(3)).toBe('/admin/organization/lawyers/3/edit')
  })

  it('generates automation paths', () => {
    expect(generatePath.quoteDetail('7')).toBe('/admin/automation/preservation-quotes/7')
    expect(generatePath.recognitionDetail('8')).toBe('/admin/automation/document-recognition/8')
  })

  it('generates template edit path', () => {
    expect(generatePath.templateEdit('1')).toBe('/admin/templates/1/edit')
  })

  it('generates court sms detail path', () => {
    expect(generatePath.courtSmsDetail(42)).toBe('/admin/tools/court-sms/42')
  })

  it('generates workbench session path', () => {
    expect(generatePath.workbenchSession('sess-123')).toBe('/admin/workbench/sess-123')
  })
})
