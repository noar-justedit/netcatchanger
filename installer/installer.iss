; NetCatChanger — Inno Setup script
; Compiled by scripts\build_windows.bat (if Inno Setup is installed) and by
; the GitHub Actions workflow (Inno Setup is preinstalled on windows runners).
; Expects dist\NetCatChanger.exe to exist (PyInstaller output).

#define MyAppName "NetCatChanger"
#define MyAppVersion "2.2.1"
#define MyAppPublisher "just edit"
#define MyAppURL "https://github.com/noar-justedit/netcatchanger"
#define MyAppExeName "NetCatChanger.exe"

[Setup]
; Stable AppId: never change it, it is how Windows recognises upgrades
AppId={{D447AA79-8F4C-4201-AE85-7783961525FE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=NetCatChanger-Setup-{#MyAppVersion}
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The app manages network profiles and the firewall: per-machine install,
; elevation asked once by the installer (the app asks again at launch)
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
; Third-party notices must ship with the binaries they cover
Source: "..\LICENSE-lucide.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\fonts\Poppins-OFL.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Per-user data stays by default; the config lives in %APPDATA%\NetCatChanger
; and is deliberately NOT removed here so settings survive a reinstall.
