param(
    [string]$PythonPath = "python"
)

Write-Host "Запуск шаблонного скрипта..." -ForegroundColor Cyan
& $PythonPath "${PSScriptRoot}\main.py"
