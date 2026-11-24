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
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
  $ver = & py -3.12 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
  if ($LASTEXITCODE -eq 0) { $py = 'py -3.12' }
}
if (-not $py) {
  $pythonExe = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonExe) {
    $ver = & python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
    if ($LASTEXITCODE -eq 0) {
      $maj, $min = $ver -split '\.'
      if ([int]$maj -ge 3 -and [int]$min -ge 12) { $py = 'python' }
    }
  }
}
if (-not $py) {
  Write-Host "   Python 3.12+ не найден — устанавливаю через winget..."
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "winget не смог установить Python.Python.3.12 (код $LASTEXITCODE). Попробуйте установить вручную с https://www.python.org/downloads/ (нужен 3.12+)." }
  $py = 'python'   # пересоздаём PATH-допускение после новой установки
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
