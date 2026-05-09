/**
 * ClientList Component
 *
 * 当事人列表组件
 * - 组合 ClientFilters 和 ClientTable
 * - 实现分页控件
 * - 实现新建按钮
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'
import { PageFooter } from '@/components/shared/PageFooter'
import { usePaginatedList } from '@/hooks/use-paginated-list'

import { ClientFilters } from './ClientFilters'
import { ClientTable } from './ClientTable'
import { clientApi } from '../api'
import type { Client, ClientType } from '../types'

const DEFAULT_PAGE_SIZE = 20

export function ClientList() {
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [clientType, setClientType] = useState<ClientType | undefined>(undefined)
  const [isOurClient, setIsOurClient] = useState<boolean | undefined>(undefined)

  const filters = {
    search: search || undefined,
    client_type: clientType,
    is_our_client: isOurClient,
  }

  const { data, isLoading, page, setPage, withPageReset } = usePaginatedList<Client, typeof filters>({
    queryKey: 'clients',
    fetchAll: (f) => clientApi.list({
      search: f.search,
      client_type: f.client_type,
      is_our_client: f.is_our_client,
    }),
    filters,
    pageSize: DEFAULT_PAGE_SIZE,
    staleTime: 5 * 60 * 1000,
  })

  const handleSearchChange = withPageReset(setSearch)
  const handleClientTypeChange = withPageReset(setClientType)
  const handleIsOurClientChange = withPageReset(setIsOurClient)
  const handleCreateClick = useCallback(() => { navigate(PATHS.ADMIN_CLIENT_NEW) }, [navigate])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ClientFilters
          search={search}
          onSearchChange={handleSearchChange}
          clientType={clientType}
          onClientTypeChange={handleClientTypeChange}
          isOurClient={isOurClient}
          onIsOurClientChange={handleIsOurClientChange}
        />

        <Button onClick={handleCreateClick} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />
          新建当事人
        </Button>
      </div>

      <ClientTable clients={data.items} isLoading={isLoading} />

      <PageFooter
        stats={[{ label: '共', value: `${data.total} 条` }]}
        page={page}
        total={data.total}
        pageSize={DEFAULT_PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  )
}

export default ClientList
