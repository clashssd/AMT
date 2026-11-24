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
    Если только что поставленный (через winget) инструмент ещё не виден в ТЕКУЩЕМ сеансе
    (стандартная ситуация: PATH-снапшот процесса зафиксирован до установки) — скрипт САМ,
    без вашего участия и без просьбы «перезапустите терминал», автоматически перезапускает
    себя в новом процессе powershell.exe (чистый, пост-установочный PATH) и продолжает
    работу — вам не нужно вводить ничего повторно, с первого же запуска идёт до конца.
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

function Test-Python312Plus([string[]]$cmdParts) {
  # Запускаем команду (массив аргументов, чтобы не зависеть от кавычек) и проверяем major.minor >= 3.12
  try {
    $ver = & $cmdParts -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
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
if ($pyLauncher -and (Test-Python312Plus @('py','-3'))) {
  $py = 'py -3'
}

# 1b) обычный python на PATH
if (-not $py) {
  $pythonExe = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonExe -and (Test-Python312Plus @('python'))) {
    $py = 'python'
  }
}

# 1c) Известное место per-user установки winget/официального установщика,
#     даже если python ещё не на PATH в текущем сеансе (типовая ситуация после
#     winget per-user install без перезапуска PATH):
if (-not $py) {
  $localPy = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
  if ((Test-Path $localPy) -and (Test-Python312Plus @($localPy))) {
    $py = $localPy
    Write-Host "   Найдено: $localPy (per-user установка, ещё не в PATH)" -ForegroundColor Yellow
  }
}

# 1d) Не найден -> ставим через winget. ВАЖНО: не верим слепо коду возврата winget
#     (он может ненулевое вернуть, даже если пакет УЖЕ установлен/установлен вручную) —
#     после вызова winget В ЛЮБОМ случае перепроверяем наличие рабочего Python;
#     ошибка только если Python реально не появился ни в одном из известных мест.
if (-not $py) {
  Write-Host "   Python 3.12+ не найден — устанавливаю через winget..."
  try {
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements | Out-Null
  } catch {
    Write-Host "   (winget вернул ошибку/предупреждение, продолжаю и перепроверяю фактическое наличие)" -ForegroundColor Yellow
  }
  $wingetCode = $LASTEXITCODE

  # Перепроверяем ВСЕ варианты (py-лаунчер + PATH + известное per-user место), независимо от кода winget.
  # ВАЖНО: обязательно перепроверяем ТАКЖЕ "py -3" (системный лаунчер, не зависит от user-PATH),
  # т.к. winget/установщик Python по умолчанию регистрирует python с py-лаунчером даже когда
  # сам "python.exe" не попадает в PATH (например, корпоративный/ограниченный аккаунт).
  if (Get-Command py -ErrorAction SilentlyContinue -and (Test-Python312Plus @('py','-3'))) {
    $py = 'py -3'
  } else {
    $freshByPath = Get-Command python -ErrorAction SilentlyContinue
    if ($freshByPath -and (Test-Python312Plus @('python'))) {
      $py = 'python'
    } else {
      $localPy = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
      if ((Test-Path $localPy) -and (Test-Python312Plus @($localPy))) {
        $py = $localPy
      }
    }
  }

  if (-not $py) {
    # Свежая установка winget обычно не видна в ТЕКУЩЕМ процессе (PATH-снапшот
    # этого powershell.exe зафиксирован ДО установки) — не просим пользователя
    # вручную перезапускать терминал, а автоматически перезапускаем СЕБЯ в
    # НОВОМ процессе powershell.exe (у него чистый, пост-установочный PATH).
    # Защита от бесконечного цикла: перезапускаемся максимум 1 раз.
    if (-not $env:AMT_BOOTSTRAP_RETRY) {
      Write-Host "   Python установлен, но ещё не виден в этом сеансе — автоматически перезапущу скрипт в новом контексте (без вашего участия)..." -ForegroundColor Yellow
      $env:AMT_BOOTSTRAP_RETRY = '1'
      & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
      exit $LASTEXITCODE
    }
    if ($wingetCode -ne 0) {
      Fail "winget не смог установить Python.Python.3.12 (код $wingetCode), и Python не найден ни в PATH, ни в ``$env:LOCALAPPDATA\Programs\Python\Python312``. Установите вручную с https://www.python.org/downloads/ (нужен 3.12+) и перезапустите скрипт."
    } else {
      Fail "Python 3.12 установлен через winget, но не обнаружен даже после автоматического перезапуска в новом контексте — возможно, установка не завершилась (проверьте %LOCALAPPDATA%\Programs\Python), или поставьте вручную (https://www.python.org/downloads/) и перезапустите скрипт."
    }
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
  if (-not $node) {
    # Та же ситуация, что с Python: свежая winget-установка не видна в ТЕКУЩЕМ
    # процессе (PATH-снапшот зафиксирован до установки). Не просим вручную
    # перезапускать терминал — автоматически перезапускаем себя в новом
    # powershell.exe (чистый пост-установочный PATH), максимум 1 раз.
    if (-not $env:AMT_BOOTSTRAP_RETRY) {
      Write-Host "   Node.js установлен, но ещё не виден в этом сеансе — автоматически перезапущу скрипт в новом контексте (без вашего участия)..." -ForegroundColor Yellow
      $env:AMT_BOOTSTRAP_RETRY = '1'
      & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
      exit $LASTEXITCODE
    }
    Fail "Node.js установлен через winget, но не обнаружен даже после автоматического перезапуска в новом контексте — возможно, установка не завершилась (проверьте winget-логи), или поставьте вручную (https://nodejs.org) и перезапустите скрипт."
  }
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
