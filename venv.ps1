param(
    [string]$VenvPath = ".venv",
    [string]$PythonExecutable = "python"
)

Write-Host "🚀 Настройка виртуального окружения в PowerShell" -ForegroundColor Cyan
Write-Host "Папка окружения: $VenvPath"

if (-not (Test-Path $PythonExecutable) -and $PythonExecutable -eq "python") {
    $PythonExecutable = "py"
}

if (-not (Get-Command $PythonExecutable -ErrorAction SilentlyContinue)) {
    Write-Error "Не найден исполняемый файл Python ($PythonExecutable). Установите Python и добавьте его в PATH."
    exit 1
}

if (-not (Test-Path $VenvPath)) {
    Write-Host "Создаю виртуальное окружение..." -ForegroundColor Yellow
    & $PythonExecutable -m venv $VenvPath
} else {
    Write-Host "Виртуальное окружение уже существует, пропускаю создание." -ForegroundColor Yellow
}

$VenvPython = Join-Path $VenvPath "Scripts\\python.exe"
$ActivateScript = Join-Path $VenvPath "Scripts\\Activate.ps1"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Не удалось найти python.exe внутри окружения ($VenvPython). Проверьте корректность установки."
    exit 1
}

if (Test-Path "requirements.txt") {
    Write-Host "Устанавливаю зависимости из requirements.txt..." -ForegroundColor Yellow
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements.txt
} else {
    Write-Warning "Файл requirements.txt не найден, пропускаю установку зависимостей."
}

Write-Host "Готово! Чтобы активировать окружение в текущей сессии PowerShell, выполните:" -ForegroundColor Green
Write-Host ". `"$ActivateScript`"" -ForegroundColor Green
