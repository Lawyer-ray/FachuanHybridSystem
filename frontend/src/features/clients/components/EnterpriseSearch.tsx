/**
 * EnterpriseSearch - 企业信息搜索预填组件
 */

import { useState, useCallback } from 'react'
import {
  Search, Building2, Loader2, CheckCircle2, AlertTriangle, ExternalLink, Sparkles,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

import { clientApi } from '../api'
import type { EnterpriseCompany, EnterprisePrefillData, EnterpriseProfile } from '../types'

interface Props {
  onPrefill: (data: EnterprisePrefillData) => void
}

const PROVIDERS = [
  { value: 'tianyancha', label: '天眼查' },
]

const expandAnim = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1, transition: { height: { duration: 0.25 }, opacity: { duration: 0.2, delay: 0.05 } } },
  exit: { height: 0, opacity: 0, transition: { opacity: { duration: 0.15 }, height: { duration: 0.2, delay: 0.05 } } },
}

export function EnterpriseSearch({ onPrefill }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [provider, setProvider] = useState('tianyancha')
  const [keyword, setKeyword] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [isLoadingPrefill, setIsLoadingPrefill] = useState(false)
  const [companies, setCompanies] = useState<EnterpriseCompany[]>([])
  const [selectedCompany, setSelectedCompany] = useState<EnterpriseCompany | null>(null)
  const [profile, setProfile] = useState<EnterpriseProfile | null>(null)
  const [prefillData, setPrefillData] = useState<EnterprisePrefillData | null>(null)
  const [existingClient, setExistingClient] = useState<{ id: number; name: string } | null>(null)
  const [searchError, setSearchError] = useState('')

  const handleSearch = useCallback(async () => {
    const kw = keyword.trim()
    if (!kw) { setSearchError('请输入企业名称关键词'); return }
    setIsSearching(true)
    setSearchError('')
    setSelectedCompany(null)
    setProfile(null)
    setPrefillData(null)
    setExistingClient(null)
    try {
      const result = await clientApi.searchEnterprise(kw, provider)
      setCompanies(result.items)
      if (!result.items.length) setSearchError('暂未检索到匹配企业，可换关键词继续搜索')
    } catch {
      setSearchError('企业搜索失败，请重试')
      setCompanies([])
    } finally {
      setIsSearching(false)
    }
  }, [keyword, provider])

  const handleSelect = useCallback(async (company: EnterpriseCompany) => {
    setSelectedCompany(company)
    setIsLoadingPrefill(true)
    try {
      const result = await clientApi.getEnterprisePrefill(company.company_id, provider)
      setProfile(result.profile)
      setPrefillData(result.prefill)
      setExistingClient(result.existing_client)
    } catch {
      toast.error('企业详情加载失败')
    } finally {
      setIsLoadingPrefill(false)
    }
  }, [provider])

  const handleApply = useCallback(() => {
    if (!prefillData) return
    onPrefill(prefillData)
    toast.success('已自动填充企业信息')
  }, [prefillData, onPrefill])

  return (
    <div className="group relative overflow-hidden rounded-xl border border-blue-200/60 bg-gradient-to-br from-blue-50/80 via-white to-sky-50/50 shadow-sm transition-shadow hover:shadow-md dark:border-blue-800/40 dark:from-blue-950/30 dark:via-gray-950 dark:to-sky-950/20">
      {/* 顶部装饰线 */}
      <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-blue-400 via-sky-400 to-cyan-400" />

      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center justify-between px-5 py-3.5"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-sky-500 shadow-sm">
            <Building2 className="size-4 text-white" />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">企业信息搜索预填</span>
              <Badge variant="secondary" className="border-blue-200/60 bg-blue-100/60 text-[11px] text-blue-700 dark:border-blue-800/40 dark:bg-blue-900/40 dark:text-blue-300">
                法人 / 非法人组织
              </Badge>
            </div>
            <p className="text-muted-foreground mt-0.5 text-xs">搜索企业名称，一键回填工商信息</p>
          </div>
        </div>
        <motion.div
          animate={{ rotate: expanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="text-muted-foreground"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </motion.div>
      </button>

      {/* Content */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div {...expandAnim} className="overflow-hidden">
            <div className="space-y-4 px-5 pb-5">
              {/* 搜索栏 */}
              <div className="flex flex-col gap-2 sm:flex-row">
                <Select value={provider} onValueChange={setProvider}>
                  <SelectTrigger className="h-10 w-full border-blue-200/60 bg-white/80 sm:w-36 dark:border-blue-800/40 dark:bg-gray-900/60"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PROVIDERS.map((p) => (
                      <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="flex flex-1 gap-2">
                  <Input
                    placeholder="输入企业名称关键词..."
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    className="h-10 border-blue-200/60 bg-white/80 dark:border-blue-800/40 dark:bg-gray-900/60"
                  />
                  <Button onClick={handleSearch} disabled={isSearching} size="sm" className="h-10 shrink-0 bg-gradient-to-r from-blue-500 to-sky-500 px-4 text-white shadow-sm hover:from-blue-600 hover:to-sky-600">
                    {isSearching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
                    <span className="ml-1.5 hidden sm:inline">搜索</span>
                  </Button>
                </div>
              </div>

              {searchError && (
                <p className="text-muted-foreground text-sm">{searchError}</p>
              )}

              {/* 搜索结果 */}
              <AnimatePresence mode="wait">
                {companies.length > 0 && !selectedCompany && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="max-h-64 space-y-2 overflow-y-auto"
                  >
                    {companies.map((c, i) => (
                      <motion.button
                        key={c.company_id}
                        type="button"
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className="hover:border-blue-300 hover:bg-blue-50/60 dark:hover:border-blue-700 dark:hover:bg-blue-950/30 w-full rounded-lg border border-transparent bg-white/70 px-4 py-3 text-left shadow-sm transition-all dark:bg-gray-900/50"
                        onClick={() => handleSelect(c)}
                      >
                        <div className="flex items-center gap-2">
                          <Building2 className="text-muted-foreground size-3.5 shrink-0" />
                          <span className="text-sm font-semibold">{c.company_name}</span>
                        </div>
                        <p className="text-muted-foreground mt-1 pl-5.5 text-xs">
                          法人：{c.legal_person || '-'} · 状态：{c.status || '-'} · 注册资本：{c.registered_capital || '-'}
                        </p>
                      </motion.button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* 加载中 */}
              {isLoadingPrefill && (
                <div className="flex items-center justify-center py-8">
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="size-6 animate-spin text-blue-500" />
                    <span className="text-muted-foreground text-xs">正在加载企业详情...</span>
                  </div>
                </div>
              )}

              {/* 企业详情 + 预填 */}
              <AnimatePresence>
                {profile && prefillData && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="space-y-4 rounded-xl border border-blue-100 bg-white/90 p-5 shadow-sm dark:border-blue-900/40 dark:bg-gray-900/70"
                  >
                    {existingClient && (
                      <div className="flex items-start gap-2.5 rounded-lg border border-amber-200/80 bg-amber-50/80 p-3 text-sm dark:border-amber-900/50 dark:bg-amber-950/30">
                        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" />
                        <div>
                          <p className="font-medium text-amber-800 dark:text-amber-200">该企业已存在对应当事人</p>
                          <a href={`/admin/clients/${existingClient.id}`} className="text-primary mt-1 inline-flex items-center gap-1 text-xs hover:underline">
                            查看「{existingClient.name}」<ExternalLink className="size-3" />
                          </a>
                        </div>
                      </div>
                    )}

                    <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                      {([
                        ['企业名称', profile.company_name],
                        ['统一社会信用代码', profile.unified_social_credit_code],
                        ['法定代表人', profile.legal_person],
                        ['经营状态', profile.status],
                        ['成立日期', profile.establish_date],
                        ['注册资本', profile.registered_capital],
                        ['联系电话', profile.phone],
                        ['地址', profile.address],
                      ] as const).map(([label, value]) => (
                        <div key={label} className="flex items-baseline gap-2 text-sm">
                          <span className="text-muted-foreground shrink-0 text-xs">{label}</span>
                          <span className="font-medium">{value || '-'}</span>
                        </div>
                      ))}
                    </div>

                    <div className="flex items-center justify-end gap-2 border-t pt-4">
                      <Button variant="outline" size="sm" onClick={() => { setSelectedCompany(null); setProfile(null); setPrefillData(null) }}>
                        重新搜索
                      </Button>
                      <Button size="sm" className="bg-gradient-to-r from-blue-500 to-sky-500 text-white shadow-sm hover:from-blue-600 hover:to-sky-600" onClick={handleApply}>
                        <Sparkles className="mr-1.5 size-3.5" />一键填充
                      </Button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
