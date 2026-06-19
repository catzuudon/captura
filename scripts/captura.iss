; Inno Setup script — builds Captura-<version>-windows-setup.exe
; Prerequisite: scripts\build_windows.bat has produced dist\Captura\
; Build: iscc /DAppVersion=1.0.0 scripts\captura.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppName=Captura
AppVersion={#AppVersion}
AppPublisher=Captura
DefaultDirName={autopf}\Captura
DefaultGroupName=Captura
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\Captura.exe
OutputDir=..\dist
OutputBaseFilename=Captura-{#AppVersion}-windows-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\Captura\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Captura"; Filename: "{app}\Captura.exe"
Name: "{group}\Uninstall Captura"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Captura"; Filename: "{app}\Captura.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Captura.exe"; Description: "Launch Captura"; Flags: nowait postinstall skipifsilent
