/**
 * OrganizationTabs Component
 *
 * 组织管理 Tab 切换组件
 * - 渲染四个 Tab：律所、律师、团队、凭证
 * - 根据 activeTab 显示对应的列表组件
 * - 点击 Tab 时更新 URL 参数
 *
 * Requirements:
 * - 1.1: 页面顶部显示四个 Tab：律所、律师、团队、凭证
 * - 1.2: 点击 Tab 切换显示对应的列表内容
 * - 1.3: Tab 切换时 URL 参数同步更新
 */

import { useCallback } from 'react'
import { useSearchParams } from 'react-router'
import { Building2, Users, UsersRound, KeyRound } from 'lucide-react'

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

import { LawFirmList } from './LawFirmList'
import { LawyerList } from './LawyerList'
import { TeamList } from './TeamList'
import { CredentialList } from './CredentialList'

// ============================================================================
// Constants
// ============================================================================

/** Tab 值类型 */
export type OrganizationTabValue =
  | 'lawfirms'
  | 'lawyers'
  | 'teams'
  | 'credentials'

/** 默认 Tab */
const DEFAULT_TAB: OrganizationTabValue = 'lawfirms'

/** URL 参数名 */
const TAB_PARAM_NAME = 'tab'

/** Tab 配置 */
const TAB_CONFIG: Array<{
  value: OrganizationTabValue
  label: string
  icon: React.ComponentType<{ className?: string }>
}> = [
  { value: 'lawfirms', label: '律所', icon: Building2 },
  { value: 'lawyers', label: '律师', icon: Users },
  { value: 'teams', label: '团队', icon: UsersRound },
  { value: 'credentials', label: '凭证', icon: KeyRound },
]

/** 有效的 Tab 值集合 */
const VALID_TAB_VALUES = new Set<string>(TAB_CONFIG.map((tab) => tab.value))

// ============================================================================
// Types
// ============================================================================

export interface OrganizationTabsProps {
  /**
   * 初始激活的 Tab（可选）
   * 如果不传，则从 URL 参数读取，默认为 'lawfirms'
   */
  defaultTab?: OrganizationTabValue
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 验证并返回有效的 Tab 值
 * @param value - 待验证的值
 * @param fallback - 无效时的回退值
 */
function getValidTabValue(
  value: string | null | undefined,
  fallback: OrganizationTabValue = DEFAULT_TAB
): OrganizationTabValue {
  if (value && VALID_TAB_VALUES.has(value)) {
    return value as OrganizationTabValue
  }
  return fallback
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 组织管理 Tab 切换组件
 *
 * Requirements:
 * - 1.1: 页面顶部显示四个 Tab：律所、律师、团队、凭证
 * - 1.2: 点击 Tab 切换显示对应的列表内容
 * - 1.3: Tab 切换时 URL 参数同步更新
 */
export function OrganizationTabs({ defaultTab }: OrganizationTabsProps) {
  // ========== URL 参数管理 ==========
  const [searchParams, setSearchParams] = useSearchParams()

  // 从 URL 参数获取当前 Tab，如果无效则使用默认值
  const currentTab = getValidTabValue(
    searchParams.get(TAB_PARAM_NAME),
    defaultTab ?? DEFAULT_TAB
  )

  // ========== 事件处理 ==========

  /**
   * 处理 Tab 切换
   * Requirements: 1.2, 1.3
   */
  const handleTabChange = useCallback(
    (value: string) => {
      const validValue = getValidTabValue(value)

      // 更新 URL 参数
      setSearchParams(
        (prev) => {
          const newParams = new URLSearchParams(prev)
          if (validValue === DEFAULT_TAB) {
            // 如果是默认 Tab，移除参数以保持 URL 简洁
            newParams.delete(TAB_PARAM_NAME)
          } else {
            newParams.set(TAB_PARAM_NAME, validValue)
          }
          return newParams
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  // ========== 渲染 ==========
  return (
    <Tabs
      value={currentTab}
      onValueChange={handleTabChange}
      className="w-full"
    >
      {/* Tab 列表 - Requirements: 1.1, 6.6 (支持横向滚动) */}
      <TabsList
        variant="line"
        className="mb-4 w-full justify-start overflow-x-auto sm:w-auto"
      >
        {TAB_CONFIG.map(({ value, label, icon: Icon }) => (
          <TabsTrigger
            key={value}
            value={value}
            className="min-h-[44px] min-w-[80px] gap-2 px-4"
          >
            <Icon className="size-4" />
            <span>{label}</span>
          </TabsTrigger>
        ))}
      </TabsList>

      {/* Tab 内容 - Requirements: 1.2 */}
      <TabsContent value="lawfirms">
        <LawFirmList />
      </TabsContent>

      <TabsContent value="lawyers">
        <LawyerList />
      </TabsContent>

      <TabsContent value="teams">
        <TeamList />
      </TabsContent>

      <TabsContent value="credentials">
        <CredentialList />
      </TabsContent>
    </Tabs>
  )
}

export default OrganizationTabs
