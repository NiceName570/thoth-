import { registry } from '@/contrib/registry'

import { ROUTES_AREA, type RouteContribution, SIDEBAR_NAV_AREA, type SidebarNavContribution } from '../routes'

import { MEMORIES_ROUTE, MemoriesPage } from './index'

// Contributed nav rows render after the built-ins, which end with Scheduled jobs,
// so this lands directly under it.
registry.registerMany([
  {
    id: 'memories.page',
    area: ROUTES_AREA,
    title: 'Memories',
    data: { path: MEMORIES_ROUTE } satisfies RouteContribution,
    render: () => <MemoriesPage />
  },
  {
    id: 'memories.nav',
    area: SIDEBAR_NAV_AREA,
    data: { codicon: 'book', label: 'Memories', path: MEMORIES_ROUTE } satisfies SidebarNavContribution
  }
])
