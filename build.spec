# -*- mode: python ; coding: utf-8 -*-
"""
Vox AI Input — PyInstaller 打包配置

用法:
    pip install pyinstaller pyinstaller-hooks-contrib
    pyinstaller build.spec --clean --noconfirm

输出:
    dist/VoxAIInput/（目录模式，含 VoxAIInput.exe + _internal/）

    后续步骤:
    1. python scripts/post_build.py  — 生成 app-update.zip + update-manifest.json
    2. iscc installer.iss            — 生成 Inno Setup 安装包
"""

from PyInstaller.utils.hooks import collect_submodules

# 收集 pynput 和 pystray 的所有子模块（它们使用动态 import 加载平台后端）
hidden_imports = (
    collect_submodules("pynput")
    + collect_submodules("pystray")
    + [
        # 双保险：显式指定 Windows 后端
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pynput._util.win32",
        "pystray._win32",
        # CFFI（sounddevice/soundfile 的底层依赖）
        "cffi",
        "_cffi_backend",
    ]
)

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        # 提示音资源（只读，打包到 bundle 内部）
        ("assets/sounds/*.wav", "assets/sounds"),
        # 图标
        ("assets/icon.png", "assets"),
        # 配置模板（供用户复制）
        ("config.example.yaml", "."),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大包，减小体积
        "matplotlib",
        "scipy",
        "pandas",
        "notebook",
        "IPython",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# --onedir 模式：exe + _internal/ 目录
# 相比 --onefile：启动更快（不需解压），支持增量更新
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # 关键：binaries/datas 放到 COLLECT 中
    name="VoxAIInput",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VoxAIInput",
)
