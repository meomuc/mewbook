; Inno Setup 6 script for the MewBook ("Mèo Mực") Windows installer.
;
; Normally built by packaging\build.ps1, which passes the version from
; src\smartdoc\__init__.py:   ISCC.exe /DMyAppVersion=1.0.0 packaging\MewBook.iss
; Expects the PyInstaller output in dist\MewBook\ and packaging\EULA.txt
; (both produced by build.ps1).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "Mèo Mực (MewBook)"
#define MyAppPublisher "Anhtiensinh"
#define MyAppExeName "MewBook.exe"
; Must match core.config.APP_DIR_NAME -- the per-user data folder.
#define MyDataDirName "SmartDocLibrary"

[Setup]
; AppId identifies this product to Windows forever -- NEVER change it, or
; upgrades will install side by side instead of replacing the old version.
AppId={{4820F9B0-69C6-4B0B-8445-DFD0FFA84F35}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=© 2026 {#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={autopf}\MewBook
DefaultGroupName=MewBook
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, and the uninstaller runs as the same
; user, so {userappdata} below points at *their* data folder.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=EULA.txt
OutputDir=..\dist\installer
OutputBaseFilename=MewBook-Setup-{#MyAppVersion}
SetupIconFile=..\src\smartdoc\presentation\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\MewBook\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The anonymous user identity (core/user_identity.py) lives only as long as
; the installation: uninstalling removes it, so a reinstall starts with a
; brand-new identity. The library itself is kept unless the user opts in
; below.
Type: files; Name: "{userappdata}\{#MyDataDirName}\identity.dat"
Type: files; Name: "{userappdata}\{#MyDataDirName}\mewbook.lock"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#MyDataDirName}');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('Do you also want to delete your MewBook library data (catalog, covers, settings and logs)?' + #13#10 +
                'Your original ebook files are never touched either way.' + #13#10#13#10 +
                'Xóa luôn dữ liệu thư viện (danh mục, ảnh bìa, cài đặt, nhật ký)? File sách gốc của bạn không bị ảnh hưởng.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
