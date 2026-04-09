/**
 * Client Feature Module - 统一导出
 */

// Components
export { ClientList } from './components/ClientList'
export { ClientDetail } from './components/ClientDetail'
export { ClientForm } from './components/ClientForm'
export { ClientTable } from './components/ClientTable'
export { ClientFilters } from './components/ClientFilters'
export { IdentityDocList } from './components/IdentityDocList'
export { IdentityDocManager } from './components/IdentityDocManager'
export { OcrUploader } from './components/OcrUploader'
export { PropertyClueList } from './components/PropertyClueList'
export { PropertyClueFormDialog } from './components/PropertyClueFormDialog'
export { EnterpriseSearch } from './components/EnterpriseSearch'
export { TextParser } from './components/TextParser'

// Hooks
export { useClients } from './hooks/use-clients'
export { useClient } from './hooks/use-client'
export { useClientMutations } from './hooks/use-client-mutations'
export { usePropertyClues } from './hooks/use-property-clues'
export { usePropertyClueMutations } from './hooks/use-property-clue-mutations'
export { useIdentityDocMutations } from './hooks/use-identity-doc-mutations'

// Types
export type {
  ClientType, DocType, ClueType,
  Client, ClientInput, IdentityDoc, IdentityDocDetail,
  PropertyClue, PropertyClueInput, PropertyClueAttachment,
  EnterpriseCompany, EnterpriseSearchResult, EnterpriseProfile,
  EnterprisePrefillData, EnterprisePrefillResult,
  ParseTextResult,
  ClientListParams, ClientListResponse, PaginatedResponse,
  OcrRecognizeResult, OcrResult, ApiError, ClientFormMode,
} from './types'

export {
  CLIENT_TYPE_LABELS, DOC_TYPE_LABELS, CLUE_TYPE_LABELS,
  NATURAL_DOC_TYPES, LEGAL_DOC_TYPES,
} from './types'

// API
export { clientApi } from './api'
export { default as clientApiDefault } from './api'
