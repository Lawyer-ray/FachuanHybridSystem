import { createFeatureApiClient } from '@/lib/api'
import type { FolderBinding, FolderBrowseResponse, FolderScanStart, FolderScanSubfolderList, FolderScanStatus, FolderScanConfirmItem, FolderScanConfirmResult } from '../types'

const client = createFeatureApiClient('contracts')

export const foldersApi = {
  getBinding: async (contractId: number): Promise<FolderBinding | null> =>
    client.get(`${contractId}/folder-binding`).json<FolderBinding | null>(),

  createBinding: async (
    contractId: number,
    params: { folder_path: string; storage_type?: string; storage_account_id?: number | null },
  ): Promise<FolderBinding> =>
    client.post(`${contractId}/folder-binding`, { json: params }).json<FolderBinding>(),

  deleteBinding: async (contractId: number): Promise<{ success: boolean; message: string }> =>
    client.delete(`${contractId}/folder-binding`).json(),

  browse: async (
    path?: string,
    includeHidden = false,
    storageType?: string,
    storageAccountId?: number,
  ): Promise<FolderBrowseResponse> => {
    const sp = new URLSearchParams()
    if (path) sp.set('path', path)
    if (includeHidden) sp.set('include_hidden', 'true')
    if (storageType && storageType !== 'local') sp.set('storage_type', storageType)
    if (storageAccountId) sp.set('storage_account_id', String(storageAccountId))
    return client.get('folder-browse', { searchParams: sp }).json<FolderBrowseResponse>()
  },

  startScan: async (contractId: number, rescan = false, scanSubfolder = ''): Promise<FolderScanStart> =>
    client.post(`${contractId}/folder-scan`, { json: { rescan, scan_subfolder: scanSubfolder } }).json<FolderScanStart>(),

  listScanSubfolders: async (contractId: number): Promise<FolderScanSubfolderList> =>
    client.get(`${contractId}/folder-scan/subfolders`).json<FolderScanSubfolderList>(),

  getScanStatus: async (contractId: number, sessionId: string): Promise<FolderScanStatus> =>
    client.get(`${contractId}/folder-scan/${sessionId}`).json<FolderScanStatus>(),

  confirmScan: async (contractId: number, sessionId: string, items: FolderScanConfirmItem[]): Promise<FolderScanConfirmResult> =>
    client.post(`${contractId}/folder-scan/${sessionId}/confirm`, { json: { items } }).json<FolderScanConfirmResult>(),

  listCloudStorageAccounts: async (): Promise<Array<{ id: number; name: string; storage_type: string }>> =>
    client.get('cloud-storage-accounts').json(),
}
