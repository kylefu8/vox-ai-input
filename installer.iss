; Vox AI Input — Inno Setup 安装脚本
;
; 用法（需先安装 Inno Setup 6）:
;   1. pyinstaller build.spec --clean --noconfirm
;   2. python scripts/post_build.py
;   3. iscc installer.iss
;
; 产物: release/VoxAIInput-Setup-{version}.exe

#define MyAppName "Vox AI Input"
#define MyAppExeName "VoxAIInput.exe"
#define MyAppPublisher "kylefu8"
#define MyAppURL "https://github.com/kylefu8/vox-ai-input"

; 从 run.py 读取版本号（简化：硬编码，CI 中动态替换）
#define MyAppVersion "0.0.2"

[Setup]
AppId={{A7E3F2B1-8C4D-4E5F-9A6B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\VoxAIInput
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=release
OutputBaseFilename=VoxAIInput-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; 安装时关闭正在运行的实例
CloseApplications=yes
CloseApplicationsFilter=VoxAIInput.exe
; 卸载时也关闭
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"
Name: "autostart"; Description: "开机自动启动"; GroupDescription: "附加选项:"

[Files]
; 主程序（exe + _internal/ 目录）
Source: "dist\VoxAIInput\VoxAIInput.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\VoxAIInput\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; 配置模板（仅首次安装时复制，不覆盖用户已有的 config.yaml）
Source: "config.example.yaml"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.example.yaml"; DestDir: "{app}"; DestName: "config.yaml"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 开机自启动（可选）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "VoxAIInput"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 安装完成后启动程序
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载前关闭程序
Filename: "taskkill"; Parameters: "/f /im {#MyAppExeName}"; Flags: runhidden

[UninstallDelete]
; 卸载时清理日志等临时文件（保留 config.yaml 让用户决定）
Type: filesandordirs; Name: "{app}\__pycache__"
