; Programme d'installation HA Taskbar (Inno Setup 6)
; Ne pas compiler directement : utiliser build.ps1, qui fournit AppVersion et DistDir.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\build\dist"
#endif

[Setup]
AppId={{6B0F3C2E-8F4A-4C61-9E0B-2D7A51C4B9E3}
AppName=HA Taskbar
AppVersion={#AppVersion}
AppVerName=HA Taskbar {#AppVersion}
AppPublisher=bbtoff
AppPublisherURL=https://github.com/bbtoff/home-assistant-taskbar
; Installation pour l'utilisateur courant : pas de droits administrateur
; ({autopf} = %LOCALAPPDATA%\Programs)
PrivilegesRequired=lowest
DefaultDirName={autopf}\HA Taskbar
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=HATaskbar-Setup-{#AppVersion}
SetupIconFile=..\assets\ha_taskbar.ico
UninstallDisplayIcon={app}\HATaskbar.exe
UninstallDisplayName=HA Taskbar
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "startup"; Description: "Lancer HA Taskbar au démarrage de Windows"
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; Flags: unchecked

[Files]
Source: "{#DistDir}\HATaskbar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\HA Taskbar"; Filename: "{app}\HATaskbar.exe"
Name: "{autodesktop}\HA Taskbar"; Filename: "{app}\HATaskbar.exe"; Tasks: desktopicon

[Registry]
; Meme entree que la case « Lancer au démarrage » des réglages
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "HATaskbar"; ValueData: """{app}\HATaskbar.exe"""; Tasks: startup

[Run]
Filename: "{app}\HATaskbar.exe"; Description: "Lancer HA Taskbar"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopRunningApp();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im HATaskbar.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Sleep(300);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningApp();
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Case décochée lors d'une mise à jour : on retire le démarrage automatique
  if (CurStep = ssPostInstall) and not WizardIsTaskSelected('startup') then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'HATaskbar');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  CfgDir: String;
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'HATaskbar');
  if CurUninstallStep = usPostUninstall then
  begin
    CfgDir := ExpandConstant('{userappdata}\HATaskbar');
    if DirExists(CfgDir) and not UninstallSilent() then
      if MsgBox('Supprimer aussi vos réglages (adresse, jeton d''accès et éléments) ?' + #13#10 +
                CfgDir, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(CfgDir, True, True, True);
  end;
end;
