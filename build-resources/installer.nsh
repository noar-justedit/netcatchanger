; NetCatChanger 3.x: additions to the installer made by electron-builder
; (electron-builder.yml, nsis.include). Runs when the installer starts.
;
; Migration from 2.x, which was installed by Inno Setup (AppId
; {D447AA79-8F4C-4201-AE85-7783961525FE}) into the same Program Files folder:
;  1. uninstall 2.x silently, so there are never two NetCatChanger installed
;     side by side. Its settings and IP presets in %APPDATA%\NetCatChanger are
;     not touched (2.x never removed them, 3.x reads them as they are);
;  2. remove 2.x's "Launch with Windows" (a scheduled task, and an older Run
;     entry): 3.x keeps nothing resident, and the task would start an exe
;     that no longer exists.

!define NCC_INNO_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\{D447AA79-8F4C-4201-AE85-7783961525FE}_is1"

!macro customInit
  SetRegView 64
  ReadRegStr $0 HKLM "${NCC_INNO_KEY}" "UninstallString"
  StrCmp $0 "" 0 ncc_old_found
  SetRegView 32
  ReadRegStr $0 HKLM "${NCC_INNO_KEY}" "UninstallString"
  StrCmp $0 "" ncc_old_done ncc_old_found

  ncc_old_found:
    DetailPrint "Removing NetCatChanger 2.x"
    ExecWait '$0 /VERYSILENT /SUPPRESSMSGBOXES /NORESTART'
    ; Inno's uninstaller may finish in a second process: wait (30 s at most)
    ; until its entry is gone before installing into the same folder.
    StrCpy $1 0
    ncc_old_wait:
      ReadRegStr $2 HKLM "${NCC_INNO_KEY}" "UninstallString"
      StrCmp $2 "" ncc_old_done
      IntOp $1 $1 + 1
      IntCmp $1 60 ncc_old_done
      Sleep 500
      Goto ncc_old_wait

  ncc_old_done:
  SetRegView 64

  nsExec::Exec '"$SYSDIR\schtasks.exe" /Delete /TN "NetCatChanger" /F'
  Pop $3
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "NetCatChanger"
!macroend
