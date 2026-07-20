const { execFileSync } = require('node:child_process')
const path = require('node:path')

const port = '5174'
const backendPort = '8007'
const projectFrontend = path.resolve(__dirname, '..').toLowerCase()
const repoRoot = path.resolve(__dirname, '..', '..')
const backendDir = path.join(repoRoot, 'backend')
const backendDevScript = path.join(backendDir, 'dev.ps1')
const backendOutLog = path.join(backendDir, 'server-8007.out.log')
const backendErrLog = path.join(backendDir, 'server-8007.err.log')

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

  const backendOutput = runPowerShell(`
    Get-NetTCPConnection -LocalPort ${backendPort} -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  `)

  const backendIsRunning = lines(backendOutput).some(Boolean)

  if (!backendIsRunning) {
    const escapedBackendDir = backendDir.replace(/'/g, "''")
    const escapedBackendDevScript = backendDevScript.replace(/'/g, "''")
    const escapedOutLog = backendOutLog.replace(/'/g, "''")
    const escapedErrLog = backendErrLog.replace(/'/g, "''")
    runPowerShell(`
      Start-Process -FilePath powershell.exe \
        -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','${escapedBackendDevScript}' \
        -WorkingDirectory '${escapedBackendDir}' \
        -RedirectStandardOutput '${escapedOutLog}' \
        -RedirectStandardError '${escapedErrLog}' \
        -WindowStyle Hidden
    `)
    console.log(`Backend iniciado en http://127.0.0.1:${backendPort}.`)
  }
}
