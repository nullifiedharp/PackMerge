; PackMerge installer - built by build.bat (Inno Setup 6)
; Copyright (C) 2026 NullHarp - GPLv3

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "PackMerge"
#define MyAppExe "PackMerge.exe"
#define MyAppPublisher "NullHarp"
#define MyAppURL "https://github.com/nullifiedharp/PackMerge"
#define VerbText "Merge into one .mcaddon"

[Setup]
AppId={{A449AB24-6191-4A3B-9259-E87F1873388E}
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
; per-user install: no admin prompt, and the right-click entry lives in HKCU
PrivilegesRequired=lowest
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=PackMerge-Setup-{#MyAppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
CloseApplications=yes

[Tasks]
Name: "contextmenu"; Description: "Add ""{#VerbText}"" to the right-click menu for .mcaddon and .mcpack files"; GroupDescription: "Integration:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\PackMerge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; clean up the entry left by the pre-release script, if any
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcaddon\shell\McaddonMerger"; ValueType: none; Flags: deletekey dontcreatekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcpack\shell\McaddonMerger"; ValueType: none; Flags: deletekey dontcreatekey

; .mcaddon
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcaddon\shell\PackMerge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "{#VerbText}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcaddon\shell\PackMerge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExe}"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcaddon\shell\PackMerge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcaddon\shell\PackMerge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: contextmenu

; .mcpack
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcpack\shell\PackMerge"; ValueType: string; ValueName: "MUIVerb"; ValueData: "{#VerbText}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcpack\shell\PackMerge"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExe}"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcpack\shell\PackMerge"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mcpack\shell\PackMerge\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; also removes the menu entry if it was switched on from inside the app
Filename: "{app}\{#MyAppExe}"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveContextMenu"
