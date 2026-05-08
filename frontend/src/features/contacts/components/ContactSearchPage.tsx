/**
 * ContactSearchPage - 全局联系人搜索页面
 */

import { useState } from 'react'
import { Search, Users, Phone, MapPin, Building2 } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Card, CardContent } from '@/components/ui/card'

import { useContactSearch } from '../hooks/use-contact-search'
import { CONTACT_ROLE_LABELS } from '../types'

export function ContactSearchPage() {
  const [query, setQuery] = useState('')
  const [court, setCourt] = useState('')
  const [role, setRole] = useState('')

  const { data: results, isLoading } = useContactSearch({
    q: query || undefined,
    court: court || undefined,
    role: role || undefined,
  })

  return (
    <div className="container mx-auto py-6 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Users className="size-6" />
          联系人搜索
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          跨案件搜索公检法工作人员联系方式，数据来自全体律师的共享
        </p>
      </div>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                placeholder="搜索姓名..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <Input
              placeholder="法院/机关名称"
              value={court}
              onChange={(e) => setCourt(e.target.value)}
              className="sm:w-48"
            />
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger className="sm:w-36">
                <SelectValue placeholder="角色" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">全部角色</SelectItem>
                {Object.entries(CONTACT_ROLE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>{label.zh}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {isLoading && (
        <div className="text-center py-12 text-muted-foreground">搜索中...</div>
      )}

      {results && results.length === 0 && (query || court || role) && (
        <div className="text-center py-12 text-muted-foreground">未找到匹配的联系人</div>
      )}

      {results && results.length > 0 && (
        <div className="space-y-3">
          {results.map((item, idx) => (
            <Card key={idx}>
              <CardContent className="py-4">
                <div className="flex items-start gap-3">
                  <div className="bg-muted flex size-10 shrink-0 items-center justify-center rounded-full">
                    <Users className="text-muted-foreground size-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{item.name}</span>
                      <Badge variant="secondary" className="text-[11px]">
                        {item.role_display || item.role}
                      </Badge>
                      {item.authority_name && (
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                          <Building2 className="size-3" />
                          {item.authority_name}
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                      {item.phone && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Phone className="size-3" /> {item.phone}
                        </span>
                      )}
                      {item.address && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <MapPin className="size-3" /> {item.address}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      出现在 {item.occurrence_count} 个案件中
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!results && !isLoading && (
        <div className="text-center py-12 text-muted-foreground">
          <Users className="size-12 mx-auto mb-3 opacity-30" />
          <p>输入关键词搜索公检法工作人员联系方式</p>
        </div>
      )}
    </div>
  )
}
