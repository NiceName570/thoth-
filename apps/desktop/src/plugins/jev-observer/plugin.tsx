/**
 * ExpressionJev settings entry.
 *
 * Registers the page that shows the plugin's own observations. The agent
 * plugin's `config_schema` form folds in automatically beneath this entry as
 * "Agent settings" (see contrib/settings-pages.ts), so the rubric knobs and
 * the observation view share one rail row.
 */

import type { HermesPlugin } from '@hermes/plugin-sdk'

import { JevObserverPage } from './view'

const plugin: HermesPlugin = {
  defaultEnabled: true,
  description: 'Read-only view of ExpressionJev: what was scored, and which turns each contextual judgment carried.',
  id: 'jev-observer',
  name: 'ExpressionJev',
  // Same package as `plugins/jev-observer` — merge the halves into one row.
  packageName: 'jev-observer',
  register(ctx) {
    ctx.registerSettingsPage({
      icon: 'eye',
      id: 'observer',
      order: 20,
      render: () => <JevObserverPage rest={ctx.rest} />,
      title: 'ExpressionJev'
    })
  }
}

export default plugin
