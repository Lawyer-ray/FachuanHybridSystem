const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPut = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn()
  return { mockGet, mockPost, mockPut, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
  })),
}))

import { partiesApi } from '../parties'

describe('cases/api/partiesApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('list calls correct endpoint with caseId', async () => {
    await partiesApi.list(1)
    expect(mockGet).toHaveBeenCalledWith('parties', { searchParams: { case_id: '1' } })
  })

  it('create posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    const data = { case_id: 1, client_id: 10, legal_status: 'plaintiff' }
    await partiesApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('parties', { json: data })
  })

  it('update puts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await partiesApi.update(1, { legal_status: 'defendant' })
    expect(mockPut).toHaveBeenCalledWith('parties/1', { json: { legal_status: 'defendant' } })
  })

  it('delete calls correct endpoint', async () => {
    await partiesApi.delete(1)
    expect(mockDelete).toHaveBeenCalledWith('parties/1')
  })

  it('listAssignments calls correct endpoint', async () => {
    await partiesApi.listAssignments(1)
    expect(mockGet).toHaveBeenCalledWith('assignments', { searchParams: { case_id: '1' } })
  })

  it('createAssignment posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await partiesApi.createAssignment({ case_id: 1, lawyer_id: 5 })
    expect(mockPost).toHaveBeenCalledWith('assignments', { json: { case_id: 1, lawyer_id: 5 } })
  })

  it('deleteAssignment calls correct endpoint', async () => {
    await partiesApi.deleteAssignment(1)
    expect(mockDelete).toHaveBeenCalledWith('assignments/1')
  })

  it('listGrants calls correct endpoint', async () => {
    await partiesApi.listGrants(1)
    expect(mockGet).toHaveBeenCalledWith('grants', { searchParams: { case_id: '1' } })
  })

  it('createGrant posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await partiesApi.createGrant({ case_id: 1, grantee_id: 5 })
    expect(mockPost).toHaveBeenCalledWith('grants', { json: { case_id: 1, grantee_id: 5 } })
  })

  it('deleteGrant calls correct endpoint', async () => {
    await partiesApi.deleteGrant(1)
    expect(mockDelete).toHaveBeenCalledWith('grants/1')
  })
})
