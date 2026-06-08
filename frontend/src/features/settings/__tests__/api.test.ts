vi.mock('@/lib/api', () => {
  const chain = () => ({
    get: vi.fn().mockReturnThis(),
    post: vi.fn().mockReturnThis(),
    put: vi.fn().mockReturnThis(),
    patch: vi.fn().mockReturnThis(),
    delete: vi.fn().mockReturnThis(),
    json: vi.fn().mockResolvedValue({}),
  })
  return {
    API_BASE_URL: 'http://localhost:8002/api/v1',
    createFeatureApiClient: vi.fn().mockReturnValue(chain()),
  }
})

import { taskQueueApi, systemConfigApi } from '../api'
import { createFeatureApiClient } from '@/lib/api'

describe('taskQueueApi', () => {
  it('listQueued fetches queued tasks', async () => {
    const client = createFeatureApiClient('task-queue') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([{ id: '1', name: 'task1' }]) })
    const result = await taskQueueApi.listQueued()
    expect(result).toEqual([{ id: '1', name: 'task1' }])
  })

  it('listCompleted fetches completed tasks', async () => {
    const client = createFeatureApiClient('task-queue') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await taskQueueApi.listCompleted()
    expect(result).toEqual([])
  })

  it('listFailed fetches failed tasks', async () => {
    const client = createFeatureApiClient('task-queue') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await taskQueueApi.listFailed()
    expect(result).toEqual([])
  })

  it('listScheduled fetches scheduled tasks', async () => {
    const client = createFeatureApiClient('task-queue') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await taskQueueApi.listScheduled()
    expect(result).toEqual([])
  })

  it('deleteTask deletes by taskId', async () => {
    const client = createFeatureApiClient('task-queue') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockReturnValue({ json: vi.fn().mockResolvedValue({ deleted: 1 }) })
    const result = await taskQueueApi.deleteTask('abc')
    expect(result).toEqual({ deleted: 1 })
  })

  it('deleteSchedule deletes by scheduleId', async () => {
    const client = createFeatureApiClient('task-queue') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockReturnValue({ json: vi.fn().mockResolvedValue({ deleted: 1 }) })
    const result = await taskQueueApi.deleteSchedule(5)
    expect(result).toEqual({ deleted: 1 })
  })

  it('resubmitTask posts to correct endpoint', async () => {
    const client = createFeatureApiClient('task-queue') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ new_task_id: 'new-1' }) })
    const result = await taskQueueApi.resubmitTask('old-1')
    expect(result).toEqual({ new_task_id: 'new-1' })
  })
})

describe('systemConfigApi', () => {
  it('listConfigs fetches config groups', async () => {
    const client = createFeatureApiClient('config') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ groups: [] }) })
    const result = await systemConfigApi.listConfigs()
    expect(result).toEqual({ groups: [] })
  })

  it('updateConfigs sends category and updates', async () => {
    const client = createFeatureApiClient('config') as unknown as { put: ReturnType<typeof vi.fn> }
    client.put.mockReturnValue({ json: vi.fn().mockResolvedValue({ success: true, updated_count: 2 }) })
    const result = await systemConfigApi.updateConfigs('email', { host: 'smtp.example.com' })
    expect(result).toEqual({ success: true, updated_count: 2 })
  })

  it('createConfig sends new config data', async () => {
    const client = createFeatureApiClient('config') as unknown as { post: ReturnType<typeof vi.fn> }
    const mockItem = { key: 'test_key', value: 'test', category: 'general' }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue(mockItem) })
    const result = await systemConfigApi.createConfig({ key: 'test_key', value: 'test', category: 'general' })
    expect(result).toEqual(mockItem)
  })

  it('patchConfig updates a single config by key', async () => {
    const client = createFeatureApiClient('config') as unknown as { patch: ReturnType<typeof vi.fn> }
    client.patch.mockReturnValue({ json: vi.fn().mockResolvedValue({ key: 'test_key' }) })
    const result = await systemConfigApi.patchConfig('test_key', { value: 'new_val' })
    expect(result).toEqual({ key: 'test_key' })
  })

  it('deleteConfig deletes by key', async () => {
    const client = createFeatureApiClient('config') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockReturnValue({ json: vi.fn().mockResolvedValue({ success: true }) })
    const result = await systemConfigApi.deleteConfig('test_key')
    expect(result).toEqual({ success: true })
  })
})
