; AgentBridge desktop installer (Inno Setup 6)
; Usage:
;   scripts\pack-desktop-installer.ps1 -CompileWithIscc -Version 1.0.0
; The staging tree (dist\installer-stage) must exist first.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "AgentBridge"
#define MyAppPublisher "AgentBridge"
#define MyAppExeName "AgentBridge.Desktop.exe"

[Setup]
AppId={{6F2E0D8A-3A7B-4C2E-9F1D-5B8A0C4E7D2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AgentBridge
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=AgentBridge-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=10.0
UninstallDisplayIcon={app}\app\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#SourcePath}\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Self-contained desktop app (no .NET runtime required on the target machine)
Source: "..\..\dist\installer-stage\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
; Backend + embedded Python runtime + adapters + bridge scripts
Source: "..\..\dist\installer-stage\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"; WorkingDir: "{app}\app"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"; WorkingDir: "{app}\app"; Tasks: desktopicon

[Run]
Filename: "{app}\app\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyAppExeName} 2>nul"; Flags: runhidden; RunOnceId: "KillRunningApp"

[Code]
function InitializeSetup(): Boolean;
begin
  // The shell renders the panel with WebView2. Warn (don't block) when the
  // Evergreen runtime is missing so the user can install it separately.
  Result := True;
  if not RegValueExists(HKLM64, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv') and
     not RegValueExists(HKLM64, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv') then
  begin
    if MsgBox('WebView2 runtime was not detected. The panel may not render.' + #13#10 +
              'Install it from https://developer.microsoft.com/microsoft-edge/webview2/ .' + #13#10#13#10 +
              'Continue the installation anyway?', mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;
