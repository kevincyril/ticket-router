# Run from the repository root after following README dependency setup.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install dependencies with uv sync --frozen first.' }
if (-not (Test-Path -LiteralPath 'artifacts\robustness\deployed\model.joblib')) { throw 'Package the robustness model first; see README.' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Build the dashboard with npm ci and npm run build in frontend first.' }
if (-not (Test-Path '.env')) { Copy-Item '.env.windows.example' '.env' }
New-Item -ItemType Directory -Force '.local' | Out-Null
& $python scripts/local_postgres.py
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL setup failed.' }
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed.' }
$localProcesses = @()
$redisIsReady = $false
try {
    $redisClient = New-Object System.Net.Sockets.TcpClient
    $redisClient.Connect('127.0.0.1',56379)
    $redisIsReady = $true
    $redisClient.Dispose()
} catch {}
if (-not $redisIsReady) {
    if (-not (Test-Path '.local\redis\redis-server.exe')) { throw 'Install local Redis per README, or use Docker Compose.' }
    $localProcesses += Start-Process -FilePath '.local\redis\redis-server.exe' -ArgumentList '--port','56379','--bind','127.0.0.1','--dir','.local/redis','--appendonly','yes' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput '.local/redis.stdout.log' -RedirectStandardError '.local/redis.stderr.log' -PassThru
}
foreach ($entry in @(@('api','-m uvicorn app.main:app --host 127.0.0.1 --port 8000'),@('worker','-m app.worker'),@('dispatcher','-m app.jobs'))) {
    $localProcesses += Start-Process -FilePath $python -ArgumentList $entry[1] -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput ".local/$($entry[0]).stdout.log" -RedirectStandardError ".local/$($entry[0]).stderr.log" -PassThru
}
$localProcesses | ForEach-Object { @{ id=$_.Id; start_time_ticks=$_.StartTime.ToUniversalTime().Ticks; executable=$_.Path } } | ConvertTo-Json | Set-Content '.local/processes.json'
Write-Output 'Relay: http://127.0.0.1:8000 ; OpenAPI: http://127.0.0.1:8000/docs'
Write-Output 'Logs: .local/*.log. Stop these owned processes with scripts/stop-local.ps1. PostgreSQL data lives in .local/postgres.'
