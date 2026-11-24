; build/nsis-clean.nsh — кастомный фрагмент NSIS для electron-builder (подключается
; через build.nsis.include в package.json).
;
; Определяет !macro customUnInstall — стандартный хук electron-builder
; (см. templates/nsis/uninstaller.nsh: `!ifmacrodef customUnInstall`),
; вызываемый автоматически в конце uninstall-секции.
;
; "Чистая" развёртка: при удалении приложения убираем и per-user runtime-данные
; (лог/чаты/ключи/память в frozen-режиме лежат под %APPDATA%\AMT Chat\),
; чтобы после удаления приложения не осталось личных данных пользователя.

!macro customUnInstall
  ; Electron всегда использует per-user app data (см. комментарий в uninstaller.nsh)
  RMDir /r "$APPDATA\AMT Chat"
!macroend
