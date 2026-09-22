; Inno Setup script для Quantis.
;
; Перед сборкой установщика нужен готовый onedir-билд от PyInstaller:
;     poetry run python packaging/scripts/build_exe.py qt
;     poetry run python packaging/scripts/build_exe.py vlc
;
; Затем:
;     poetry run python packaging/scripts/build_installer.py
;     poetry run python packaging/scripts/build_installer.py --backend vlc
;
; Приложение НЕ пишет ничего в свой каталог установки: музыка идёт в
; «Музыка\Quantis», остальные данные — в %LOCALAPPDATA%\Quantis. Поэтому
; установка в Program Files не требует прав администратора во время работы.

#ifndef Backend
  #define Backend "qt"
#endif

#ifndef AppVersion
  #error AppVersion is required. Use: poetry run python packaging/scripts/build_installer.py
#endif

#if Backend == "vlc"
  #define AppExeName "Quantis-VLC"
  #define AppSuffix " (VLC)"
#else
  #define AppExeName "Quantis"
  #define AppSuffix ""
#endif

#define AppName "Quantis" + AppSuffix
#define AppPublisher "Really-Fun"
#define AppUrl "https://github.com/Really-Fun/Quantis"
#define RepoRoot "..\.."
#define SourceDir RepoRoot + "\dist\" + AppExeName

[Setup]
AppId={{8E2F2C41-4B7D-4B1E-9E4A-3C6D5A9B7F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName=Quantis
DisableProgramGroupPage=yes
LicenseFile={#RepoRoot}\LICENSE
OutputDir={#RepoRoot}\dist\installer
OutputBaseFilename={#AppExeName}-{#AppVersion}-setup
SetupIconFile={#RepoRoot}\src\quantis\assets\icons\logo.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Права администратора нужны только на запись в Program Files при установке.
; Пользователь может выбрать установку «только для меня» — тогда всё уйдёт в
; %LOCALAPPDATA%\Programs и UAC не появится.
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}.exe
UninstallDisplayName={#AppName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "credentials,*.db,cookie.txt,cookies.txt,youtube_cookies*,portable.txt"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}.exe"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Кэш и логи, созданные приложением. Данные пользователя (музыка, плейлисты,
; история, токены) остаются — их удаление предлагаем отдельным шагом ниже.
Type: filesandordirs; Name: "{localappdata}\Quantis\cache"
Type: dirifempty; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Quantis');
    if DirExists(DataDir) then
    begin
      if MsgBox('Удалить данные Quantis (история, плейлисты, токены, плагины)?' + #13#10 +
                DataDir + #13#10#13#10 +
                'Скачанная музыка останется на месте.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
