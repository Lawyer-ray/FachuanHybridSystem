/**
 * 收件箱模块 barrel exports
 */

// Types
export type {
  InboxMessage,
  InboxMessageDetail,
  InboxListParams,
  AttachmentMeta,
} from './types'

// API
export { inboxApi } from './api'

// Hooks
export { useInboxMessage } from './hooks/use-inbox-message'

// Components
export { InboxList } from './components/InboxList'
export { InboxMessageView } from './components/InboxMessageView'
