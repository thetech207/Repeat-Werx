; Inno Setup script for Repeat-Werx (Windows)
; Build: packaging\build-windows.ps1 <version>
;   or:  iscc packaging\repeatwerx.iss /DMyAppVersion=1.0.4

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{3E8B1D47-92C6-4F0A-A5D3-6B7E2C9F1A58}
AppName=Repeat-Werx
AppVersion={#MyAppVersion}
AppPublisher=thetech207
AppPublisherURL=https://github.com/thetech207/Repeat-Werx
AppSupportURL=https://github.com/thetech207/Repeat-Werx/issues
DefaultDirName={autopf}\Repeat-Werx
DefaultGroupName=Repeat-Werx
OutputDir=..\dist
OutputBaseFilename=repeatwerx_{#MyAppVersion}_win64_setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=..\Images\repeatwerx-icon.ico
UninstallDisplayIcon={app}\repeatwerx.exe
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\repeatwerx\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Repeat-Werx"; Filename: "{app}\repeatwerx.exe"
Name: "{autodesktop}\Repeat-Werx"; Filename: "{app}\repeatwerx.exe"; Tasks: desktopicon

[Registry]
; .rwpx file association (per-user, merges into HKCR view)
Root: HKCU; Subkey: "Software\Classes\.rwpx"; ValueType: string; ValueData: "RepeatWerx.Project"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\RepeatWerx.Project"; ValueType: string; ValueData: "Repeat-Werx Project"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\RepeatWerx.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\repeatwerx.exe,0"
Root: HKCU; Subkey: "Software\Classes\RepeatWerx.Project\shell\open\command"; ValueType: string; ValueData: """{app}\repeatwerx.exe"" ""%1"""

[Run]
Filename: "{app}\repeatwerx.exe"; Description: "Launch Repeat-Werx"; Flags: nowait postinstall skipifsilent
