import { registry } from '@/contrib/registry'
import { STATUSBAR_AREAS } from '@/sdk/areas'

import { UsageMeter } from './index'

registry.register({ id: 'usage-meter', area: STATUSBAR_AREAS.right, order: 70, render: () => <UsageMeter /> })
