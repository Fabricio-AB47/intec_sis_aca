const { execFileSync } = require('node:child_process')

const port = '5174'

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

function isViteCommand(command) {
  const normalizedCommand = normalize(command).replaceAll('\\', '/')
  return (
    normalizedCommand.includes('node_modules/vite/bin/vite.js') ||
    normalizedCommand.includes('/vite/bin/vite.js') ||
    normalizedCommand.includes('vite/dist/node/cli.js') ||
    /(^|\s)(vite|vite\.cmd)(\s|$)/.test(normalizedCommand)
  )
}

function listeningPids() {
  try {
    const output = execFileSync('netstat.exe', ['-ano', '-p', 'tcp'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    const listenerPattern = new RegExp(`^\\s*TCP\\s+\\S+:${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)\\s*$`, 'i')
    return [
      ...new Set(
        lines(output)
          .map((line) => line.match(listenerPattern)?.[1])
          .filter(Boolean),
      ),
    ]
  } catch {
    return []
  }
}

function sleep(milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds)
}

if (process.platform === 'win32') {
  const pids = listeningPids()
  let foundForeignProcess = false

  for (const pid of pids) {
    const processInfo = runPowerShell(`
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=${pid}" -ErrorAction SilentlyContinue
      if ($proc) { "$($proc.ParentProcessId)|$($proc.CommandLine)" }
    `)
    const [parentPid, ...commandParts] = processInfo.split('|')
    const normalizedCommand = normalize(commandParts.join('|'))
    if (isViteCommand(normalizedCommand)) {
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
    } else {
      foundForeignProcess = true
      console.warn(
        `El puerto ${port} está ocupado por otro proceso (PID ${pid}); Vite utilizará el siguiente puerto disponible.`,
      )
    }
  }

  for (let attempt = 0; attempt < 50 && listeningPids().length > 0 && !foundForeignProcess; attempt += 1) {
    sleep(100)
  }

  if (listeningPids().length > 0) {
    console.warn(`El puerto preferido ${port} continúa ocupado.`)
  }
}
