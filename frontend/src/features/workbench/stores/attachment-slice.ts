import type { StateCreator } from 'zustand'
import type { Attachment } from '../types'
import { getAccessToken } from '@/lib/token'
import { API_BASE_URL } from '@/lib/api'
import type { WorkbenchStore } from './workbench-store'

export interface AttachmentSlice {
  attachments: Attachment[]
  addAttachment: (file: File) => Promise<void>
  removeAttachment: (id: string) => void
  clearAttachments: () => void
}

export const createAttachmentSlice: StateCreator<WorkbenchStore, [], [], AttachmentSlice> = (set) => ({
  attachments: [],

  addAttachment: async (file) => {
    const id = `att_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const attachment: Attachment = {
      id,
      name: file.name,
      type: file.type,
      size: file.size,
      status: 'uploading',
    }
    set((s) => ({ attachments: [...s.attachments, attachment] }))

    try {
      const formData = new FormData()
      formData.append('file', file)
      const token = getAccessToken()
      const resp = await fetch(`${API_BASE_URL}/workbench/attachments`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })

      if (!resp.ok) throw new Error(`上传失败: ${resp.status}`)

      const data = await resp.json() as { id: string; url?: string }
      set((s) => ({
        attachments: s.attachments.map((a) =>
          a.id === id ? { ...a, status: 'ready' as const, url: data.url, id: data.id || id } : a,
        ),
      }))
    } catch {
      try {
        const reader = new FileReader()
        const dataUrl = await new Promise<string>((resolve, reject) => {
          reader.onload = () => resolve(reader.result as string)
          reader.onerror = reject
          reader.readAsDataURL(file)
        })
        set((s) => ({
          attachments: s.attachments.map((a) =>
            a.id === id ? { ...a, status: 'ready' as const, url: dataUrl } : a,
          ),
        }))
      } catch {
        set((s) => ({
          attachments: s.attachments.map((a) =>
            a.id === id ? { ...a, status: 'error' as const, error: '文件读取失败' } : a,
          ),
        }))
      }
    }
  },

  removeAttachment: (id) => {
    set((s) => ({ attachments: s.attachments.filter((a) => a.id !== id) }))
  },

  clearAttachments: () => {
    set({ attachments: [] })
  },
})
