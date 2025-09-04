; Inno Setup Script for Gem's POS
; Cleaned and optimized version

#define MyAppName "Gem's POS"
#define MyAppVersion "2.3"
#define MyAppPublisher "RJZA Shinano29"
#define MyAppURL "https://shinano21.github.io/porfolio/"
#define MyAppExeName "Gems_POS.exe"

[Setup]
AppId={{6B7A2C3D-4E5F-6789-ABCD-EF1234567890}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=E:\Projects\POS\Output
OutputBaseFilename=Gems_POS_Setup
SetupIconFile=E:\Projects\POS\dist\images\shinano.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; 
GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: "E:\Projects\POS\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; User data (installed only if not already present)
Source: "C:\Users\U S E R -PC\AppData\Roaming\ShinanoPOS\*"; 
DestDir: "{userappdata}\ShinanoPOS"; 
Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

; Application resources
Source: "E:\Projects\POS\dist\images\*"; DestDir: "{app}\images"; 
Flags: ignoreversion recursesubdirs createallsubdirs
Source: "E:\Projects\POS\dist\images\shinano.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; 
Filename: "{app}\{#MyAppExeName}"; 
IconFilename: "{app}\shinano.ico"

Name: "{commondesktop}\{#MyAppName}"; 
Filename: "{app}\{#MyAppExeName}"; 
IconFilename: "{app}\shinano.ico"; 
Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; 
Description: "{cm:LaunchProgram,{#MyAppName}}"; 
Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{userappdata}\ShinanoPOS"; Permissions: users-modify

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Ensure write permissions on ShinanoPOS directory
    Exec('icacls.exe',
         ExpandConstant('{userappdata}\ShinanoPOS') + ' /grant:r Users:(OI)(CI)F /T',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
