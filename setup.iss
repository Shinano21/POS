; Inno Setup Script for ARI Pharma POS Installation
[Setup]
AppName=Shinano29 POS
AppVersion=1.6
AppPublisher=Shinano29
AppSupportURL=https://shinano21.github.io/POS/
DefaultDirName={autopf}\Shinano29 POS
DefaultGroupName=Shinano29 POS
OutputDir=Output
OutputBaseFilename=Shinano29POS_Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=shinano.ico
UninstallDisplayIcon={app}\shinano.ico
WizardStyle=modern
DisableProgramGroupPage=auto
PrivilegesRequired=admin

[Files]
Source: "dist\wat2.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "images\medkitpos.png"; DestDir: "{app}\images"; Flags: ignoreversion
Source: "shinano.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Shinano29 POS"; Filename: "{app}\wat2.exe"; IconFilename: "{app}\shinano.ico"
Name: "{commondesktop}\Shianano29 POS"; Filename: "{app}\wat2.exe"; IconFilename: "{app}\shinano.ico"

[Run]
Filename: "{app}\wat2.exe"; Description: "{cm:LaunchProgram,ARI Pharma POS}"; Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{app}\images"