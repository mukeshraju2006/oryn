#define MyAppName "Oryn"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Oryn"
#define MyAppExeName "Oryn.exe"

[Setup]
AppId={{8D7B8B7B-9B21-4C7C-A8A4-ORYN00000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={autopf}\Oryn
DefaultGroupName=Oryn

OutputDir=..\dist\installer
OutputBaseFilename=Oryn-Setup

Compression=lzma
SolidCompression=yes

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

WizardStyle=modern

UninstallDisplayName=Oryn
Uninstallable=yes

[Files]
Source: "..\dist\Oryn\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Oryn"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Oryn"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch Oryn"; \
    Flags: nowait postinstall skipifsilent