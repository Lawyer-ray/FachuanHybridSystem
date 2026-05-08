/** 工具调用结果结构化渲染器注册表 */

import React from 'react'
import { CaseResult } from './CaseResult'
import { CompanyResult } from './CompanyResult'
import { ContractResult } from './ContractResult'
import { ClientResult } from './ClientResult'
import { ReminderResult } from './ReminderResult'
import { ListResult } from './ListResult'

export interface ToolResultRendererProps {
  output: unknown
  input: Record<string, unknown>
  toolName: string
}

/** 根据 tool_name 渲染结构化结果，返回 null 时回退到 JSON 展示 */
export function renderToolResult(
  props: ToolResultRendererProps
): React.ReactNode | null {
  const { toolName } = props

  // ── 案件相关 ──
  if (isCaseTool(toolName)) return React.createElement(CaseResult, props)
  // ── 企业数据相关 ──
  if (isCompanyTool(toolName)) return React.createElement(CompanyResult, props)
  // ── 合同相关 ──
  if (isContractTool(toolName)) return React.createElement(ContractResult, props)
  // ── 客户相关 ──
  if (isClientTool(toolName)) return React.createElement(ClientResult, props)
  // ── 提醒/财务相关 ──
  if (isReminderTool(toolName)) return React.createElement(ReminderResult, props)
  // ── 通用列表工具 ──
  if (isListTool(toolName)) return React.createElement(ListResult, props)

  return null
}

function isCaseTool(name: string): boolean {
  return (
    name.includes('case') ||
    name.includes('party') ||
    name === 'assign_lawyer'
  )
}

function isCompanyTool(name: string): boolean {
  return (
    name.includes('company') ||
    name.includes('enterprise') ||
    name.includes('bidding') ||
    name.includes('person_profile')
  )
}

function isContractTool(name: string): boolean {
  return name.includes('contract')
}

function isClientTool(name: string): boolean {
  return name.includes('client') || name.includes('property_clue')
}

function isReminderTool(name: string): boolean {
  return (
    name.includes('reminder') ||
    name.includes('payment') ||
    name.includes('finance')
  )
}

function isListTool(name: string): boolean {
  return (
    name.startsWith('list_') ||
    name.startsWith('search_') ||
    name.startsWith('query_')
  )
}
