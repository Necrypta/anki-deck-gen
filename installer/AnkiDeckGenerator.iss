; Inno Setup script. CI builds it with:
;   ISCC.exe /DAppVersion=0.2.0 installer\AnkiDeckGenerator.iss
; Per-user install (no admin prompt). The fixed AppId lets new versions
; upgrade in place.
;
; User data (decks, settings, backups) lives in %APPDATA%\AnkiDeckGenerator,
; never in {app}. Don't add it to [UninstallDelete]: upgrades and uninstalls
; must leave it alone.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C2B9E-4A7D-4E8B-9C3A-2D5E8F1A7B40}
AppName=Anki Deck Generator
AppVersion={#AppVersion}
AppVerName=Anki Deck Generator {#AppVersion}
AppPublisher=Necrypta
AppPublisherURL=https://github.com/Necrypta/anki-deck-gen
DefaultDirName={autopf}\Anki Deck Generator
DefaultGroupName=Anki Deck Generator
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=AnkiDeckGenerator-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Anki Deck Generator
UninstallDisplayIcon={app}\AnkiDeckGenerator.exe
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\AnkiDeckGenerator.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Anki Deck Generator"; Filename: "{app}\AnkiDeckGenerator.exe"
Name: "{autodesktop}\Anki Deck Generator"; Filename: "{app}\AnkiDeckGenerator.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AnkiDeckGenerator.exe"; Description: "{cm:LaunchProgram,Anki Deck Generator}"; Flags: nowait postinstall skipifsilent
