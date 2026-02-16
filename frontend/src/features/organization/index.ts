/**
 * Organization Feature Module
 *
 * 组织管理模块的统一导出
 * 包含组件、hooks、类型定义和 API
 */

// ============================================================================
// Components
// ============================================================================

// 律所组件
export { LawFirmList } from './components/LawFirmList'
export { LawFirmTable } from './components/LawFirmTable'
export { LawFirmForm } from './components/LawFirmForm'
export { LawFirmDetail } from './components/LawFirmDetail'

// 律师组件
export { LawyerList } from './components/LawyerList'
export { LawyerTable } from './components/LawyerTable'
export { LawyerFilters } from './components/LawyerFilters'
export { LawyerForm } from './components/LawyerForm'
export { LawyerDetail } from './components/LawyerDetail'

// 团队组件
export { TeamList } from './components/TeamList'
export { TeamTable } from './components/TeamTable'
export { TeamFormDialog } from './components/TeamFormDialog'

// 凭证组件
export { CredentialList } from './components/CredentialList'
export { CredentialTable } from './components/CredentialTable'
export { CredentialFormDialog } from './components/CredentialFormDialog'

// Tab 组件
export { OrganizationTabs } from './components/OrganizationTabs'
export type { OrganizationTabValue } from './components/OrganizationTabs'

// ============================================================================
// Hooks
// ============================================================================

// 律所 hooks
export { useLawFirms } from './hooks/use-lawfirms'
export { useLawFirm } from './hooks/use-lawfirm'
export { useLawFirmMutations } from './hooks/use-lawfirm-mutations'

// 律师 hooks
export { useLawyers } from './hooks/use-lawyers'
export { useLawyer } from './hooks/use-lawyer'
export { useLawyerMutations } from './hooks/use-lawyer-mutations'

// 团队 hooks
export { useTeams } from './hooks/use-teams'
export { useTeamMutations } from './hooks/use-team-mutations'

// 凭证 hooks
export { useCredentials } from './hooks/use-credentials'
export { useCredentialMutations } from './hooks/use-credential-mutations'

// ============================================================================
// Types
// ============================================================================

export type {
  // 枚举类型
  TeamType,
  // 实体类型
  LawFirm,
  Lawyer,
  Team,
  AccountCredential,
  // API 输入类型
  LawFirmInput,
  LawFirmUpdateInput,
  LawyerCreateInput,
  LawyerUpdateInput,
  TeamInput,
  CredentialInput,
  CredentialUpdateInput,
  // API 查询参数类型
  LawyerListParams,
  TeamListParams,
  CredentialListParams,
  // 组件类型
  FormMode,
  OrganizationTab,
} from './types'

export { TEAM_TYPE_LABELS, ORGANIZATION_TAB_LABELS } from './types'

// ============================================================================
// API
// ============================================================================

export { lawFirmApi, lawyerApi, teamApi, credentialApi } from './api'
