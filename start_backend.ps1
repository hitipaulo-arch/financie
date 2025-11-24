# Script PowerShell para iniciar o backend
Write-Host "Iniciando Backend do Gestor Financeiro..." -ForegroundColor Green
Set-Location $PSScriptRoot
& "$PSScriptRoot\..\.venv\Scripts\python.exe" "$PSScriptRoot\backend.py"
