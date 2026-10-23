; Inno Setup script for the Windows installer (https://jrsoftware.org/isinfo.php).
; build.py runs it after building the programs with Nuitka:
;   ISCC /DAppVersion=2.0.0 /DSourceDir=dist\CMS-Downloader /Odist installer.iss

#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\CMS-Downloader"
#endif
#define AppName "GUC CMS Downloader"
#define AppExeName "CMS Downloader.exe"
#define AppURL "https://github.com/numberw8835/CMS-dl"

[Setup]
; Same AppId as the first installer, so installing this version replaces that one
AppId={{A3B2C1D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=numberw8835
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs for the current user without admin rights, which keeps the program folder writable for courses.json
PrivilegesRequired=lowest
OutputBaseFilename=CMS-Downloader-Setup-{#AppVersion}
SetupIconFile=gui_modules\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Add the cms-dl command to PATH (for using it from a terminal)"; GroupDescription: "Command line:"; Flags: unchecked

[InstallDelete]
; The programs of the first installer
Type: files; Name: "{app}\CMS-Downloader-GUI.exe"
Type: files; Name: "{app}\CMS-Downloader-CLI.exe"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[Code]
function InPath(Paths, Dir: string): Boolean;
begin
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') > 0;
end;

{ The "Add cms-dl to PATH" task adds the program folder to the user's PATH }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Paths, Dir: string;
begin
  if (CurStep <> ssPostInstall) or not WizardIsTaskSelected('addtopath') then
    exit;
  Dir := ExpandConstant('{app}');
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths) then
    Paths := '';
  if InPath(Paths, Dir) then
    exit;
  if (Paths <> '') and (Paths[Length(Paths)] <> ';') then
    Paths := Paths + ';';
  RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths + Dir);
end;

{ Uninstalling takes it back out }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Paths, Dir: string;
  P: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths) then
    exit;
  Dir := ExpandConstant('{app}');
  if not InPath(Paths, Dir) then
    exit;
  Paths := ';' + Paths + ';';
  P := Pos(';' + Uppercase(Dir) + ';', Uppercase(Paths));
  Delete(Paths, P, Length(Dir) + 1);
  Paths := Copy(Paths, 2, Length(Paths) - 2);
  if Paths = '' then
    RegDeleteValue(HKEY_CURRENT_USER, 'Environment', 'Path')
  else
    RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths);
end;
