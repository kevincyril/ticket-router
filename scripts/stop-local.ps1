$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$registryPath=Join-Path $projectRoot '.local/processes.json'
if (Test-Path -LiteralPath $registryPath) {
    $ownedProcesses=Get-Content -LiteralPath $registryPath -Raw | ConvertFrom-Json
    foreach ($owned in $ownedProcesses) {
        $running=Get-Process -Id $owned.id -ErrorAction SilentlyContinue
        if ($null -ne $running -and $running.StartTime.ToUniversalTime().Ticks -eq $owned.start_time_ticks -and $running.Path -eq $owned.executable -and $running.Path.StartsWith($projectRoot,[StringComparison]::OrdinalIgnoreCase)) {
            # Include the Windows supervisor's inference child, after identity checks.
            & taskkill.exe /PID $running.Id /T /F | Out-Null
        }
    }
}
$cluster=Join-Path $projectRoot '.local/postgres'
$pgCtl='C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe'
if ((Test-Path -LiteralPath (Join-Path $cluster 'PG_VERSION')) -and (Test-Path -LiteralPath $pgCtl)) {
    & $pgCtl -D $cluster stop -m fast
}
Write-Output 'Owned local services stopped. Database, Redis persistence, models and reports are retained.'
