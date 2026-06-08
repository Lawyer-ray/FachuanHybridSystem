vi.mock('@/lib/api', () => {
  const chain = () => ({
    get: vi.fn().mockReturnThis(),
    post: vi.fn().mockReturnThis(),
    put: vi.fn().mockReturnThis(),
    delete: vi.fn().mockResolvedValue(undefined),
    json: vi.fn().mockResolvedValue({}),
  })
  return {
    API_BASE_URL: 'http://localhost:8002/api/v1',
    createFeatureApiClient: vi.fn().mockReturnValue(chain()),
  }
})

import { clientApi } from '../api'
import { createFeatureApiClient } from '@/lib/api'

describe('clientApi', () => {
  it('list fetches clients with params', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await clientApi.list({ client_type: 'natural', is_our_client: true, search: 'wang' })
    expect(result).toEqual([])
  })

  it('list works with no params', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await clientApi.list()
    expect(result).toEqual([])
  })

  it('get fetches single client', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1, name: 'Wang' }) })
    const result = await clientApi.get(1)
    expect(result).toEqual({ id: 1, name: 'Wang' })
  })

  it('create sends client data', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1 }) })
    const result = await clientApi.create({ name: 'Wang', client_type: 'natural' })
    expect(result).toEqual({ id: 1 })
  })

  it('update sends updated data', async () => {
    const client = createFeatureApiClient('client') as unknown as { put: ReturnType<typeof vi.fn> }
    client.put.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1 }) })
    const result = await clientApi.update(1, { name: 'Updated', client_type: 'natural' })
    expect(result).toEqual({ id: 1 })
  })

  it('delete removes client', async () => {
    const client = createFeatureApiClient('client') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockResolvedValue(undefined)
    await clientApi.delete(5)
    expect(client.delete).toHaveBeenCalledWith('clients/5')
  })

  it('validateIdCard posts id number', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ valid: true, message: 'ok' }) })
    const result = await clientApi.validateIdCard('000000000000000100')
    expect(result).toEqual({ valid: true, message: 'ok' })
  })

  it('parseText sends text for parsing', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ success: true }) })
    const result = await clientApi.parseText('some text')
    expect(result).toEqual({ success: true })
  })

  it('searchEnterprise sends keyword', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ items: [], total: 0 }) })
    const result = await clientApi.searchEnterprise('company')
    expect(result).toEqual({ items: [], total: 0 })
  })

  it('getEnterprisePrefill sends company_id', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ prefill: {} }) })
    const result = await clientApi.getEnterprisePrefill('12345')
    expect(result).toEqual({ prefill: {} })
  })

  it('listPropertyClues fetches clues for client', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await clientApi.listPropertyClues(1)
    expect(result).toEqual([])
  })

  it('createPropertyClue sends clue data', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1 }) })
    const result = await clientApi.createPropertyClue(1, { clue_type: 'bank', content: 'test' })
    expect(result).toEqual({ id: 1 })
  })

  it('getRelatedItems fetches related cases and contracts', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ cases: [], contracts: [] }) })
    const result = await clientApi.getRelatedItems(1)
    expect(result).toEqual({ cases: [], contracts: [] })
  })

  it('checkOaCredential checks credential status', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ has_credential: true }) })
    const result = await clientApi.checkOaCredential()
    expect(result).toEqual({ has_credential: true })
  })

  it('getContentTemplate fetches template by clue type', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ clue_type: 'bank', template: '...' }) })
    const result = await clientApi.getContentTemplate('bank')
    expect(result).toEqual({ clue_type: 'bank', template: '...' })
  })

  it('addIdentityDoc uploads file with doc type', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ success: true, doc_id: 1 }) })
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    const result = await clientApi.addIdentityDoc(1, 'id_card', file)
    expect(result).toEqual({ success: true, doc_id: 1 })
  })

  it('deleteIdentityDoc deletes doc by id', async () => {
    const client = createFeatureApiClient('client') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockResolvedValue(undefined)
    await clientApi.deleteIdentityDoc(5)
    expect(client.delete).toHaveBeenCalledWith('identity-docs/5')
  })

  it('recognizeIdentityDoc sends file for OCR', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({
      json: vi.fn().mockResolvedValue({ success: true, doc_type: 'id_card', extracted_data: {}, confidence: 0.9 }),
    })
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    const result = await clientApi.recognizeIdentityDoc(file)
    expect(result.success).toBe(true)
  })

  it('submitRecognizeTask submits async task', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ task_id: 'abc', status: 'pending' }) })
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    const result = await clientApi.submitRecognizeTask(file)
    expect(result).toEqual({ task_id: 'abc', status: 'pending' })
  })

  it('getRecognizeTaskStatus checks task status', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ task_id: 'abc', status: 'completed' }) })
    const result = await clientApi.getRecognizeTaskStatus('abc')
    expect(result).toEqual({ task_id: 'abc', status: 'completed' })
  })

  it('updatePropertyClue updates clue data', async () => {
    const client = createFeatureApiClient('client') as unknown as { put: ReturnType<typeof vi.fn> }
    client.put.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1, content: 'updated' }) })
    const result = await clientApi.updatePropertyClue(1, { content: 'updated' })
    expect(result).toEqual({ id: 1, content: 'updated' })
  })

  it('deletePropertyClue deletes clue by id', async () => {
    const client = createFeatureApiClient('client') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockResolvedValue(undefined)
    await clientApi.deletePropertyClue(3)
    expect(client.delete).toHaveBeenCalledWith('property-clues/3')
  })

  it('uploadClueAttachment uploads file to clue', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1, file_name: 'test.pdf' }) })
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const result = await clientApi.uploadClueAttachment(1, file)
    expect(result).toEqual({ id: 1, file_name: 'test.pdf' })
  })

  it('deleteClueAttachment deletes attachment by id', async () => {
    const client = createFeatureApiClient('client') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockResolvedValue(undefined)
    await clientApi.deleteClueAttachment(2)
    expect(client.delete).toHaveBeenCalledWith('property-clue-attachments/2')
  })

  it('createWithDocs creates client with documents', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1, name: 'Wang' }) })
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    const result = await clientApi.createWithDocs(
      { name: 'Wang', client_type: 'natural' },
      ['id_card'],
      [file],
    )
    expect(result).toEqual({ id: 1, name: 'Wang' })
  })

  it('mergeIdCard merges front and back images', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ success: true, pdf_path: '/merged.pdf' }) })
    const front = new File(['front'], 'front.jpg', { type: 'image/jpeg' })
    const back = new File(['back'], 'back.jpg', { type: 'image/jpeg' })
    const result = await clientApi.mergeIdCard(front, back)
    expect(result).toEqual({ success: true, pdf_path: '/merged.pdf' })
  })

  it('mergeIdCardDirect merges with direct option', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ success: true }) })
    const front = new File(['front'], 'front.jpg', { type: 'image/jpeg' })
    const back = new File(['back'], 'back.jpg', { type: 'image/jpeg' })
    const result = await clientApi.mergeIdCardDirect(front, back, 1)
    expect(result).toEqual({ success: true })
  })

  it('list with partial params only sets specified params', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    await clientApi.list({ search: 'test' })
    expect(client.get).toHaveBeenCalledWith('clients', expect.objectContaining({ searchParams: expect.any(URLSearchParams) }))
  })

  it('parseText with parseMultiple flag', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ success: true }) })
    await clientApi.parseText('text', true)
    expect(client.post).toHaveBeenCalledWith('clients/parse-text', expect.objectContaining({
      json: { text: 'text', parse_multiple: true },
    }))
  })

  it('searchEnterprise with provider option', async () => {
    const client = createFeatureApiClient('client') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ items: [], total: 0 }) })
    await clientApi.searchEnterprise('company', 'tianyancha', 5)
    expect(client.get).toHaveBeenCalledWith('clients/enterprise/search', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('recognizeIdentityDoc with custom model', async () => {
    const client = createFeatureApiClient('client') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({
      json: vi.fn().mockResolvedValue({ success: true, doc_type: 'id_card', extracted_data: {}, confidence: 0.9 }),
    })
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    await clientApi.recognizeIdentityDoc(file, 'id_card', 'v2')
    expect(client.post).toHaveBeenCalledWith('identity-doc/recognize', expect.objectContaining({
      searchParams: expect.objectContaining({ doc_type: 'id_card', model: 'v2' }),
    }))
  })
})
