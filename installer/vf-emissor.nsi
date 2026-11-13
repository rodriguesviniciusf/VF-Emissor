Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!ifndef VERSION
 !define VERSION "0.20.0"
!endif
!ifndef SOURCE
 !define SOURCE ".."
!endif
!ifndef OUTPUT
 !define OUTPUT "VF-Emissor-Setup-${VERSION}.exe"
!endif
Name "VF Emissor"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\VFEmissor"
InstallDirRegKey HKCU "Software\VFEmissor" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "VF Emissor • Emissão local de NF-e"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "VF Emissor"
VIAddVersionKey "FileDescription" "Instalador VF Emissor"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "VF Emissor"
!define MUI_ABORTWARNING
!define MUI_ICON "${SOURCE}\app.ico"
!define MUI_UNICON "${SOURCE}\app.ico"
!define MUI_WELCOMEPAGE_TITLE "VF Emissor no seu computador"
!define MUI_WELCOMEPAGE_TEXT "Instale o emissor e abra pelo ícone na área de trabalho.$\r$\n$\r$\nEmpresas, configurações e XML ficam na pasta fixa do usuário do Windows. Atualizações preservam esses dados.$\r$\n$\r$\nSe você usa uma versão anterior, importe sua pasta de dados na primeira tela do programa."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchEmissor
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o VF Emissor"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"
Function LaunchEmissor
  Exec '"$INSTDIR\portable\pythonw.exe" "$INSTDIR\desktop_launcher.py"'
FunctionEnd
Var AppMutex
Var RestartApp
Function .onInit
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\VFEmissor"
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Este instalador requer Windows de 64 bits."
    Abort
  ${EndIf}
  StrCpy $RestartApp "0"
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/RESTARTAPP" $1
  ${IfNot} ${Errors}
    StrCpy $RestartApp "1"
  ${EndIf}
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\VFEmissorLocal") p .r0 ?e'
  Pop $1
  StrCpy $AppMutex $0
  ${If} $1 = 183
    System::Call 'kernel32::CloseHandle(p $AppMutex)'
    MessageBox MB_OK|MB_ICONINFORMATION "Feche o VF Emissor antes de instalar ou atualizar. Seus dados serão preservados."
    Abort
  ${EndIf}
FunctionEnd
Section "VF Emissor" SEC_APP
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r /x dados /x Dados /x __pycache__ /x .git /x .github /x installer /x scripts /x tests /x supabase /x dist /x *.pyc /x *.pfx /x *.p12 /x *.pem /x *.key /x .env* /x *.sqlite3 /x *.db /x *.exe.part "${SOURCE}\*.*"
  CreateDirectory "$SMPROGRAMS\VF Emissor"
  CreateShortCut "$DESKTOP\VF Emissor.lnk" "$INSTDIR\portable\pythonw.exe" '"$INSTDIR\desktop_launcher.py"' "$INSTDIR\app.ico" 0 SW_SHOWNORMAL "" "Emitir NF-e neste computador"
  CreateShortCut "$SMPROGRAMS\VF Emissor\VF Emissor.lnk" "$INSTDIR\portable\pythonw.exe" '"$INSTDIR\desktop_launcher.py"' "$INSTDIR\app.ico"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  CreateShortCut "$SMPROGRAMS\VF Emissor\Desinstalar.lnk" "$INSTDIR\Desinstalar.exe"
  WriteRegStr HKCU "Software\VFEmissor" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VFEmissor" "DisplayName" "VF Emissor"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VFEmissor" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VFEmissor" "Publisher" "VF Emissor"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VFEmissor" "DisplayIcon" "$INSTDIR\app.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VFEmissor" "UninstallString" '$\"$INSTDIR\Desinstalar.exe$\"'
SectionEnd
Function .onInstSuccess
  System::Call 'kernel32::CloseHandle(p $AppMutex)'
  ${If} $RestartApp = "1"
    Exec '"$INSTDIR\portable\pythonw.exe" "$INSTDIR\desktop_launcher.py"'
  ${EndIf}
FunctionEnd
Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\VF Emissor.lnk"
  RMDir /r "$SMPROGRAMS\VF Emissor"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VFEmissor"
  DeleteRegKey HKCU "Software\VFEmissor"
  RMDir /r "$INSTDIR"
  ; Nunca remover $LOCALAPPDATA\VFEmissor\Dados.
SectionEnd
