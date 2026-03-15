<#
  start.ps1 - Start backend or frontend in external terminal windows
  Usage:
    .\start.ps1 backend   - Open the FastAPI backend in a new terminal
    .\start.ps1 frontend  - Open the React dev server in a new terminal
    .\start.ps1 all       - Open both in separate terminals
#>

param(
    [ValidateSet("backend", "frontend", "all")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Internal runner (called inside the spawned window) ---
if ($env:_CRONOSAURUS_RUNNER -eq "backend") {
    $host.UI.RawUI.WindowTitle = "Cronosaurus - Backend"
    Write-Host ">> Starting backend..." -ForegroundColor Green
    Set-Location "$RootDir\backend"

    if (-not (Test-Path "venv")) {
        Write-Host "Creating Python virtual environment..."
        python -m venv venv
    }

    & "$RootDir\backend\venv\Scripts\Activate.ps1"
    pip install -q -r requirements.txt
    Write-Host "Backend running on http://localhost:8000" -ForegroundColor Green
    uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
    return
}

if ($env:_CRONOSAURUS_RUNNER -eq "frontend") {
    $host.UI.RawUI.WindowTitle = "Cronosaurus - Frontend"
    Write-Host ">> Starting frontend..." -ForegroundColor Cyan
    Set-Location "$RootDir\frontend"

    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing Node dependencies..."
        npm install
    }

    Write-Host "Frontend running on http://localhost:5173" -ForegroundColor Cyan
    npm run dev
    return
}

# --- Launcher (opens new external windows) ---
function Open-Backend {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:_CRONOSAURUS_RUNNER='backend'; & '$RootDir\start.ps1' backend"
    Write-Host "Opened backend in a new terminal window" -ForegroundColor Green
}

function Open-Frontend {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:_CRONOSAURUS_RUNNER='frontend'; & '$RootDir\start.ps1' frontend"
    Write-Host "Opened frontend in a new terminal window" -ForegroundColor Cyan
}

switch ($Target) {
    "backend"  { Open-Backend  }
    "frontend" { Open-Frontend }
    "all"      { Open-Backend; Open-Frontend }
}
