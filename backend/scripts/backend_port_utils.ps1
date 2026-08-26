function Get-ProjectBackendListeners {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
}

function Stop-ProjectBackendOnPort {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$RepoDir,

        [int]$TimeoutSeconds = 12
    )

    $listeners = @(Get-ProjectBackendListeners -Port $Port)
    if ($listeners.Count -eq 0) {
        return $false
    }

    $resolvedRepo = [System.IO.Path]::GetFullPath($RepoDir).TrimEnd('\')
    $escapedRepo = [regex]::Escape($resolvedRepo)
    $portPattern = "(?i)(?:--port(?:=|\s+)$Port)(?:\s|$)"
    $backendPattern = '(?i)(?:fastapi|uvicorn|app[\\/.]main)'
    $allProcesses = @(Get-CimInstance Win32_Process)
    $processById = @{}

    foreach ($process in $allProcesses) {
        $processById[[int]$process.ProcessId] = $process
    }

    $projectProcesses = @(
        $allProcesses | Where-Object {
            $commandLine = [string]$_.CommandLine
            $commandLine -match $escapedRepo -and
            $commandLine -match $portPattern -and
            $commandLine -match $backendPattern
        }
    )

    if ($projectProcesses.Count -eq 0) {
        $ownerList = ($listeners | ForEach-Object { $_.OwningProcess }) -join ', '
        throw "El puerto $Port esta ocupado por PID $ownerList y no corresponde al backend de este proyecto."
    }

    $projectIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($process in $projectProcesses) {
        [void]$projectIds.Add([int]$process.ProcessId)
    }

    foreach ($listener in $listeners) {
        $currentId = [int]$listener.OwningProcess
        $visited = [System.Collections.Generic.HashSet[int]]::new()
        $belongsToProject = $false

        while ($currentId -gt 0 -and $visited.Add($currentId)) {
            if ($projectIds.Contains($currentId)) {
                $belongsToProject = $true
                break
            }

            if (-not $processById.ContainsKey($currentId)) {
                break
            }

            $currentId = [int]$processById[$currentId].ParentProcessId
        }

        if (-not $belongsToProject) {
            throw "El puerto $Port incluye un proceso ajeno (PID $($listener.OwningProcess)); no se detuvo."
        }
    }

    $rootProcesses = @(
        $projectProcesses | Where-Object {
            -not $projectIds.Contains([int]$_.ParentProcessId)
        }
    )
    $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'

    foreach ($rootProcess in $rootProcesses) {
        if (Test-Path $taskkill) {
            & $taskkill /PID $rootProcess.ProcessId /T /F 2>&1 | Out-Null
        }
        else {
            Stop-Process -Id $rootProcess.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 250
        $listeners = @(Get-ProjectBackendListeners -Port $Port)
    } while ($listeners.Count -gt 0 -and (Get-Date) -lt $deadline)

    if ($listeners.Count -gt 0) {
        $ownerList = ($listeners | ForEach-Object { $_.OwningProcess }) -join ', '
        throw "No se pudo liberar el puerto $Port. PID restante(s): $ownerList."
    }

    return $true
}
