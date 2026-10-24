; Clickue installer (Inno Setup 6). Built automatically by .github/workflows/build.yml.
; Lets the user choose "Only for me" (no admin needed) or "All users" (Program Files).
; Each Windows user keeps their own jobs and settings in %APPDATA%\Clickue.

#define AppVersion GetEnv("CLICKUE_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{EFB9CCCC-73A5-4736-97D0-8718B80C9F4D}
AppName=Clickue
AppVersion={#AppVersion}
AppVerName=Clickue {#AppVersion}
AppPublisher=Clickue
DefaultDirName={autopf}\Clickue
DefaultGroupName=Clickue
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Clickue-Setup-{#AppVersion}
SetupIconFile=..\assets\clickue.ico
UninstallDisplayIcon={app}\Clickue.exe
UninstallDisplayName=Clickue
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Clickue when I sign in to Windows"; Flags: unchecked

[Files]
Source: "..\dist\Clickue.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\Clickue"; Filename: "{app}\Clickue.exe"
Name: "{group}\Uninstall Clickue"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Clickue"; Filename: "{app}\Clickue.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Clickue"; ValueData: """{app}\Clickue.exe"" --minimized"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Clickue.exe"; Description: "Start Clickue now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings and jobs in %APPDATA%\Clickue are kept on purpose (use Uninstall inside the
; app, or delete that folder, to remove them too).
