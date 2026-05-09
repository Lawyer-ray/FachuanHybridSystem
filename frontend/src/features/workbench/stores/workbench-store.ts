/** 工作台状态管理 (Zustand) */

import { create } from 'zustand'
import type { SessionSlice } from './session-slice'
import { createSessionSlice } from './session-slice'
import type { StreamingSlice } from './streaming-slice'
import { createStreamingSlice } from './streaming-slice'
import type { BatchSlice } from './batch-slice'
import { createBatchSlice } from './batch-slice'
import type { AttachmentSlice } from './attachment-slice'
import { createAttachmentSlice } from './attachment-slice'

export type WorkbenchStore = SessionSlice & StreamingSlice & BatchSlice & AttachmentSlice

export const useWorkbenchStore = create<WorkbenchStore>()((...args) => ({
  ...createSessionSlice(...args),
  ...createStreamingSlice(...args),
  ...createBatchSlice(...args),
  ...createAttachmentSlice(...args),
}))
