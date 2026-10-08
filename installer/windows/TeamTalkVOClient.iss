; Inno-Setup-Skript für den Windows-Installer von TeamTalk VO Client (seit v11.2.1).
; Aufruf in der CI:  ISCC.exe /DMyAppVersion=11.2.1 installer\windows\TeamTalkVOClient.iss
; Quelle: PyInstaller-Ausgabe "dist\TeamTalk VO Client\".

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "TeamTalk VO Client"
#define MyAppExe "TeamTalk VO Client.exe"

[Setup]
; Feste AppId: Updates ersetzen die vorhandene Installation statt eine zweite anzulegen.
AppId={{A3D85D3C-0AFA-43C6-BE12-1C2EC7312A82}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Florian Lichteblau (Flarion)
AppPublisherURL=https://github.com/fla-rion/TeamTalk-VO-Client
AppSupportURL=https://github.com/fla-rion/TeamTalk-VO-Client/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Standard: nur für den aktuellen Nutzer (keine Benutzerkontensteuerung).
; Wer für alle Nutzer installieren will, wählt das im ersten Dialog – dann
; fragt Windows nach Administratorrechten.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=TeamTalk-VO-Client-{#MyAppVersion}-windows-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExe}
; Läuft die App noch, schließt das Setup sie (Restart Manager).
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\TeamTalk VO Client\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
