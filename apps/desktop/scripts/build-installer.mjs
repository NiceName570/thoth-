// Wraps the app that scripts/bundles/desktop.py packed into release/win-unpacked (Electron plus
// the bundled Python payload) into Thoth's Windows installer: one per-machine NSIS .exe that
// installs to Program Files with a Start menu shortcut and an uninstaller. The NSIS settings
// live in electron-builder.config.cjs (`nsis`), so this only points the builder at the
// prepackaged app.
//
//   node scripts/build-installer.mjs [--app release/win-unpacked] [--version 0.1.0]
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const { values } = parseArgs({ options: { app: { type: 'string' }, version: { type: 'string' } } })
const app = path.resolve(desktop, values.app ?? 'release/win-unpacked')
const version = values.version ?? JSON.parse(fs.readFileSync(path.join(desktop, 'package.json'), 'utf8')).version

if (!fs.existsSync(path.join(app, 'resources', 'agent-payload'))) {
  throw new Error(`${app} is not a bundled build (no resources/agent-payload); run scripts/bundles/desktop.py first`)
}

// The package exports only its API; its CLI sits beside dist/ as cli.js (its `bin`).
const cli = path.join(path.dirname(createRequire(import.meta.url).resolve('electron-builder')), '..', 'cli.js')
const result = spawnSync(
  process.execPath,
  [cli, '--config', 'electron-builder.config.cjs', '--prepackaged', app, '--win', 'nsis', '--x64',
    '--publish', 'never', `-c.extraMetadata.version=${version}`],
  // The installer carries the plain Thoth identity (product-identity.cjs, bundled variant).
  { cwd: desktop, stdio: 'inherit', env: { ...process.env, HERMES_DESKTOP_VARIANT: 'bundled' } }
)

process.exitCode = result.status ?? 1
