/**
 * Client Feature Module
 *
 * 当事人管理模块的统一导出
 * 包含组件、hooks、类型定义和 API
 */

// ============================================================================
// Components
// ============================================================================

export { ClientList } from './components/ClientList'
export { ClientDetail } from './components/ClientDetail'
export { ClientForm } from './components/ClientForm'
export { ClientTable } from './components/ClientTable'
export { ClientFilters } from './components/ClientFilters'
export { IdentityDocList } from './components/IdentityDocList'
export { OcrUploader } from './components/OcrUploader'

// ============================================================================
// Hooks
// ============================================================================

export { useClients } from './hooks/use-clients'
export { useClient } from './hooks/use-client'
export { useClientMutations } from './hooks/use-client-mutations'

// ============================================================================
// Types
// ============================================================================

export type {
  // 枚举类型
  ClientType,
  DocType,
  // 实体类型
  Client,
  ClientInput,
  IdentityDoc,
  // API 类型
  ClientListParams,
  ClientListResponse,
  PaginatedResponse,
  OcrRecognizeResult,
  OcrResult,
  ApiError,
  // 组件 Props 类型
  ClientFormMode,
} from './types'

export { CLIENT_TYPE_LABELS, DOC_TYPE_LABELS } from './types'

// ============================================================================
// API
// ============================================================================

export { clientApi } from './api'
export { default as clientApiDefault } from './api'
