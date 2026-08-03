const { execFileSync } = require('node:child_process')
const path = require('node:path')

const port = '5174'
const projectFrontend = path.resolve(__dirname, '..').toLowerCase()

function runPowerShell(script) {
  try {
    return execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
  } catch {
    return ''
  }
}

function normalize(value) {
  return String(value || '').trim().toLowerCase()
}

function lines(output) {
  return String(output || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

if (process.platform === 'win32') {
  const output = runPowerShell(`
    Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  `)

  const pids = lines(output)

  for (const pid of pids) {
    const processInfo = runPowerShell(`
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=${pid}" -ErrorAction SilentlyContinue
      if ($proc) { "$($proc.ParentProcessId)|$($proc.CommandLine)" }
    `)
    const [parentPid, ...commandParts] = processInfo.split('|')
    const normalizedCommand = normalize(commandParts.join('|'))
    if (normalizedCommand.includes(projectFrontend) && normalizedCommand.includes('vite')) {
      runPowerShell(`Stop-Process -Id ${pid} -Force -ErrorAction SilentlyContinue`)
      if (parentPid && /^\d+$/.test(parentPid.trim())) {
        runPowerShell(`
          $parent = Get-CimInstance Win32_Process -Filter "ProcessId=${parentPid.trim()}" -ErrorAction SilentlyContinue
          if ($parent -and ($parent.Name -eq 'cmd.exe' -or $parent.Name -eq 'powershell.exe' -or $parent.Name -eq 'pwsh.exe')) {
            Stop-Process -Id ${parentPid.trim()} -Force -ErrorAction SilentlyContinue
          }
        `)
      }
      console.log(`Puerto ${port}: proceso Vite anterior cerrado (${pid}).`)
    }
  }
}
