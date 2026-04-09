/**
 * Case Feature Module - 统一导出
 */

// Components
export { CaseList } from './components/CaseList'
export { CaseDetail } from './components/CaseDetail'
export { CaseForm } from './components/CaseForm'
export { CaseTable } from './components/CaseTable'
export { CaseFilters } from './components/CaseFilters'
export { CasePartySection } from './components/CasePartySection'
export { CaseAssignmentSection } from './components/CaseAssignmentSection'
export { CaseLogSection } from './components/CaseLogSection'
export { CaseNumberSection } from './components/CaseNumberSection'
export { AuthoritySection } from './components/AuthoritySection'
export { CauseSelector } from './components/CauseSelector'
export { FeeCalculator } from './components/FeeCalculator'

// Hooks
export { useCases } from './hooks/use-cases'
export { useCase } from './hooks/use-case'
export { useCaseSearch } from './hooks/use-case-search'
export { useCaseMutations } from './hooks/use-case-mutations'
export { usePartyMutations } from './hooks/use-party-mutations'
export { useAssignmentMutations } from './hooks/use-assignment-mutations'
export { useLogMutations } from './hooks/use-log-mutations'
export { useCaseNumberMutations } from './hooks/use-case-number-mutations'
export { useAuthorityMutations } from './hooks/use-authority-mutations'
export { useCauseSearch, useCausesTree, useCourtSearch, useCalculateFee } from './hooks/use-reference-data'

// Types
export type {
  SimpleCaseType, CaseStatus, CaseStage, LegalStatus, AuthorityType, CaseLogReminderType,
  Case, CaseInput, CaseUpdate, CaseCreateFull,
  CaseParty, CaseAssignment, CaseLog, CaseLogAttachment, CaseLogReminder,
  CaseNumber, SupervisingAuthority,
  LawyerDetail, ClientDetail,
  CauseItem, CauseTreeNode, CourtItem,
  FeeCalculationRequest, FeeCalculationResponse,
  CaseListParams, CaseFormData,
} from './types'

export {
  SIMPLE_CASE_TYPE_LABELS, CASE_STATUS_LABELS, CASE_STAGE_LABELS,
  LEGAL_STATUS_LABELS, AUTHORITY_TYPE_LABELS, CASE_LOG_REMINDER_TYPE_LABELS,
  caseFormSchema,
} from './types'

// API
export { caseApi } from './api'
