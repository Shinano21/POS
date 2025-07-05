; Inno Setup script for ARI Pharma POS
[Setup]
AppName=ARI Pharma POS
AppVersion=1.0
AppPublisher=ARI Pharma
DefaultDirName={autopf}\ARI Pharma POS
DefaultGroupName=ARI Pharma POS
OutputDir=Output
OutputBaseFilename=ARIPharmaPOS_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\wat2.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "images\medkitpos.png"; DestDir: "{app}\images"; Flags: ignoreversion
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ARI Pharma POS"; Filename: "{app}\wat2.exe"
Name: "{commondesktop}\ARI Pharma POS"; Filename: "{app}\wat2.exe"

[Run]
Filename: "{app}\wat2.exe"; Description: "{cm:LaunchProgram,ARI Pharma POS}"; Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{app}\images"