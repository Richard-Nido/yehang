#define Version "0.1.0-beta.2"
[Setup]
AppId={{64E6063B-B74A-489A-AF0E-304C92A5DD31}
AppName=夜航
AppVersion={#Version}
AppPublisher=夜航
AppPublisherURL=https://github.com/Richard-Nido/yehang
DefaultDirName={localappdata}\Programs\Yehang
DefaultGroupName=夜航
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Compression=lzma2/fast
SolidCompression=yes
SetupIconFile=yehang.ico
UninstallDisplayIcon={app}\Yehang.exe
OutputDir={#OutDir}
#ifdef OfficeDir
OutputBaseFilename=Yehang-{#Version}-Windows-x64-Office-Setup
#else
OutputBaseFilename=Yehang-{#Version}-Windows-x64-Setup
#endif
[Languages]
Name: "zhcn"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
#ifdef OfficeDir
Name: "office"; Description: "安装夜航专用 Office 排班转换组件"; Flags: checkedonce
#endif
[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef OfficeDir
Source: "{#OfficeDir}\*"; DestDir: "{app}\office"; Excludes: "help\*,share\extensions\dict-*\*"; Tasks: office; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#OfficeDir}\..\System64\*.dll"; DestDir: "{app}\office\program"; Tasks: office; Flags: ignoreversion
#endif
[Icons]
Name: "{group}\夜航"; Filename: "{app}\Yehang.exe"
Name: "{autodesktop}\夜航"; Filename: "{app}\Yehang.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Yehang.exe"; Description: "打开夜航"; Flags: nowait postinstall skipifsilent
