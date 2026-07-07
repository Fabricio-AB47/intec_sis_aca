const { spawnSync } = require('node:child_process')
const path = require('node:path')

const scriptPath = path.resolve(__dirname, '../../backend/scripts/ensure_backend_8002.ps1')

const result = spawnSync(
  'powershell.exe',
  ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', scriptPath],
  { stdio: 'inherit' },
)

if (result.status !== 0) {
  process.exit(result.status ?? 1)
}
