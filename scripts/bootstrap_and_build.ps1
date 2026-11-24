#Requires -Version 5.1
<#
.SYNOPSIS
    AMT Chat — «с нуля» бутстрап + сборка. Один скрипт: проверит/поставит Python и Node.js
    (если их нет), создаст backend/.venv, поставит все зависимости и соберёт AMT Chat.exe
    + NSIS-инсталлятор. Для разработчика/CI, у которого может не быть тулчейна вообще.

.DESCRIPTION
    Шаги:
      1. Python 3.12+ (winget install, если нет)
      2. Node.js LTS   (winget install, если нет)
      3. python setup.py          -> backend/.venv + requirements + PyInstaller
      4. node setup.js            -> npm install
      5. node scripts/build.js all-> dist/amt-backend/ (PyInstaller) + release/ (electron-builder)
      6. node scripts/patch_exe_icon.js "<release\win-unpacked\AMT Chat.exe>"
         (обход известного бага electron-builder 25.1.8: он молча не встраивает кастомную
          иконку, поэтому добавляем её вручную в уже собранный .exe)

    Идемпотентен: если Python/Node уже стоят — не переставляет. Безопасно повторный запуск.
    Только Windows. Нужен запуск с правами, если winget-установка требует повышения
    (обычно winget ставит в per-user scope, без UAC — но проверьте, если не сработает).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bootstrap_and_build.ps1
#>

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail([string]$msg) { Write-Host "`n[ОШИБКА] $msg" -ForegroundColor Red; exit 1 }

# ---------- 0. Проверка winget ----------
$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) { Fail "winget не найден (нужен для авто-установки Python/Node, если их нет). Установите Windows 10/11 с winget, или поставьте Python+Node вручную и запускайте шаги вручную (см. docs/SETUP.md)." }

# ---------- 1. Python 3.12+ ----------
Step "Проверяю Python 3.12+"
$py = $null

function Test-Python312Plus([string]$cmd) {
  # $cmd = 'py -3', 'python', etc. — запускаем и проверяем major.minor >= 3.12
  try {
    $ver = & $cmd -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
  } catch { return $false }
  if ($LASTEXITCODE -ne 0 -or -not $ver) { return $false }
  $parts = $ver -split '\.'
  if ($parts.Count -lt 2) { return $false }
  $maj = [int]$parts[0]; $min = [int]$parts[1]
  return ($maj -ge 3 -and $min -ge 12)
}

# 1a) py-лаунчер: пробваем ЛЮБОЙ Python 3 (py -3 = самый высокий установленный 3.x),
#     а не жёстко "py -3.12" — у лаунчера может быть зарегистрирован только 3.14 (или другой),
#     без конкретного алиаса "-3.12", и тогда "py -3.12" упадёт (exit 103), хотя подходящий
#     интерпретатор 3.12+ на самом деле есть.
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher -and (Test-Python312Plus 'py -3')) {
  $py = 'py -3'
}

# 1b) обычный python на PATH
if (-not $py) {
  $pythonExe = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonExe -and (Test-Python312Plus 'python')) {
    $py = 'python'
  }
}

# 1c) Не найден -> ставим через winget
if (-not $py) {
  Write-Host "   Python 3.12+ не найден — устанавливаю через winget..."
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "winget не смог установить Python.Python.3.12 (код $LASTEXITCODE). Попробуйте установить вручную с https://www.python.org/downloads/ (нужен 3.12+)." }
  # PATH после новой winget-установки в ТЕКУЩЕМ окне терминала не обновится —
  # нужно перезапустить скрипт в новом окне (та же логика, что и для Node ниже).
  $freshPython = Get-Command python -ErrorAction SilentlyContinue
  if ($freshPython -and (Test-Python312Plus 'python')) {
    $py = 'python'
  } else {
    Fail "Python 3.12 установлен через winget, но не появился в PATH в ТЕКУЩЕМ окне — перезапустите скрипт в НОВОМ окне терминала (PATH обновится)."
  }
}
Write-Host "   Python найден/установлен: $py"

# ---------- 2. Node.js LTS ----------
Step "Проверяю Node.js (LTS)"
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
  Write-Host "   Node.js не найден — устанавливаю через winget..."
  winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "winget не смог установить OpenJS.NodeJS.LTS (код $LASTEXITCODE). Попробуйте вручную: https://nodejs.org (нужен 18+)." }
  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) { Fail "Node.js всё ещё не в PATH после установки — перезапустите скрипт в НОВОМ окне терминала (PATH обновится)." }
}
$nodeVer = & node --version
Write-Host "   Node.js найден/установлен: $nodeVer"

# ---------- 3. Python venv + requirements + PyInstaller ----------
Step "Создаю/обновляю backend/.venv + ставлю requirements (включая PyInstaller)"
& $py setup.py
if ($LASTEXITCODE -ne 0) { Fail "python setup.py завершился с ошибкой (код $LASTEXITCODE)." }

# ---------- 4. npm install ----------
Step "npm install (зависимости frontend/electron)"
& node setup.js
if ($LASTEXITCODE -ne 0) { Fail "node setup.js (npm install) завершился с ошибкой (код $LASTEXITCODE)." }

# ---------- 5. Сборка: PyInstaller + electron-builder ----------
Step "Собираю дистрибутив: PyInstaller (dist/amt-backend) + electron-builder (release/ NSIS)"
& node scripts\build.js all
if ($LASTEXITCODE -ne 0) { Fail "node scripts/build.js all завершился с ошибкой (код $LASTEXITCODE)." }

# ---------- 6. Патч кастомной иконки в собранный .exe (обход бага electron-builder) ----------
Step "Патчу кастомную иконку AMT в release\win-unpacked\AMT Chat.exe (известный обход)"
$exe = Join-Path $Root 'release\win-unpacked\AMT Chat.exe'
if (-not (Test-Path $exe)) { Fail "Не найден $exe — сборка не завершена?" }
& node scripts\patch_exe_icon.js $exe
if ($LASTEXITCODE -ne 0) { Write-Host "   (предупреждение) патч иконки не прошёл — сам .exe работает, иконка может остаться стандартной" -ForegroundColor Yellow }

Step "Готово!"
Write-Host @"

Где что лежит:
  • Портативный (без установки) :  release\win-unpacked\AMT Chat.exe
  • Классический NSIS-инсталлятор:  release\AMT Chat Setup <версия>.exe

Можно запускать AMT Chat.exe прямо сейчас — ничего дополнительно ставить не нужно.
"@
