"""
构建后处理脚本

在 PyInstaller --onedir 构建完成后运行，生成增量更新包：
1. 从 dist/VoxAIInput/_internal/ 中提取"我们的代码"部分
2. 打包为 app-update.zip（~100-200KB）
3. 生成 update-manifest.json（版本号 + SHA256 + 文件列表）

用法:
    pyinstaller build.spec --clean --noconfirm
    python scripts/post_build.py

产物（放到 release/ 目录）:
    release/app-update.zip          — 增量更新包
    release/update-manifest.json    — 更新清单
"""

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# PyInstaller 输出目录
DIST_DIR = PROJECT_ROOT / "dist" / "VoxAIInput"
INTERNAL_DIR = DIST_DIR / "_internal"

# 发布产物目录
RELEASE_DIR = PROJECT_ROOT / "release"

# 属于"我们的代码"的文件/目录模式（相对于 _internal/）
# 这些是增量更新时需要替换的文件
APP_PATTERNS = [
    "run.pyc",              # 主入口编译文件
    "src/**",               # 我们的所有源码模块
    "assets/**",            # 资源文件（提示音等）
    "config.example.yaml",  # 配置模板
]


def _get_version():
    """从 run.py 读取版本号。"""
    run_py = PROJECT_ROOT / "run.py"
    for line in run_py.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            # __version__ = "0.1.0"
            return line.split("=")[1].strip().strip('"').strip("'")
    return "0.0.0"


def _sha256_file(path):
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_app_files():
    """
    收集属于"我们的代码"的文件列表。

    Returns:
        list[Path]: 文件路径列表（相对于 _internal/）
    """
    files = []

    # src/ 目录下所有文件
    src_dir = INTERNAL_DIR / "src"
    if src_dir.exists():
        for f in src_dir.rglob("*"):
            if f.is_file():
                files.append(f.relative_to(INTERNAL_DIR))

    # assets/ 目录下所有文件
    assets_dir = INTERNAL_DIR / "assets"
    if assets_dir.exists():
        for f in assets_dir.rglob("*"):
            if f.is_file():
                files.append(f.relative_to(INTERNAL_DIR))

    # _internal 根目录下的特定文件
    for name in ["config.example.yaml"]:
        p = INTERNAL_DIR / name
        if p.exists():
            files.append(Path(name))

    # run.pyc（可能在 _internal/ 根目录或其他位置）
    # PyInstaller --onedir 会把入口脚本编译后放在 _internal/ 下
    for f in INTERNAL_DIR.glob("run*"):
        if f.is_file() and f.suffix in (".pyc", ".py"):
            files.append(f.relative_to(INTERNAL_DIR))

    return sorted(set(files))


def main():
    """主函数。"""
    print("=" * 50)
    print("Vox AI Input — 构建后处理")
    print("=" * 50)

    # 检查构建目录
    if not DIST_DIR.exists():
        print(f"错误: 构建目录不存在: {DIST_DIR}")
        print("请先运行: pyinstaller build.spec --clean --noconfirm")
        sys.exit(1)

    if not INTERNAL_DIR.exists():
        print(f"错误: _internal 目录不存在: {INTERNAL_DIR}")
        sys.exit(1)

    version = _get_version()
    print(f"版本: v{version}")

    # 收集应用文件
    app_files = _collect_app_files()
    if not app_files:
        print("警告: 没有找到应用文件，跳过增量包生成")
        return

    print(f"应用文件数: {len(app_files)}")
    for f in app_files:
        print(f"  {f}")

    # 创建 release 目录
    RELEASE_DIR.mkdir(exist_ok=True)

    # 1. 生成 app-update.zip
    zip_path = RELEASE_DIR / "app-update.zip"
    print(f"\n生成增量更新包: {zip_path}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel_path in app_files:
            full_path = INTERNAL_DIR / rel_path
            zf.write(full_path, str(rel_path))

    zip_size = zip_path.stat().st_size
    print(f"  大小: {zip_size / 1024:.1f} KB")

    # 2. 生成 update-manifest.json
    manifest = {
        "version": version,
        "assets": {
            "app-update.zip": {
                "size": zip_size,
                "sha256": _sha256_file(zip_path),
            },
        },
        "files": {},
    }

    # 记录每个文件的哈希（用于未来更细粒度的增量）
    for rel_path in app_files:
        full_path = INTERNAL_DIR / rel_path
        manifest["files"][str(rel_path)] = {
            "size": full_path.stat().st_size,
            "sha256": _sha256_file(full_path),
        }

    manifest_path = RELEASE_DIR / "update-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"清单: {manifest_path}")

    # 3. 复制 config.example.yaml 到 release/（安装包需要）
    example_cfg = PROJECT_ROOT / "config.example.yaml"
    if example_cfg.exists():
        shutil.copy2(example_cfg, RELEASE_DIR / "config.example.yaml")

    print(f"\n完成！产物在 {RELEASE_DIR}/")
    print(f"  app-update.zip        ({zip_size / 1024:.1f} KB) — 增量更新包")
    print(f"  update-manifest.json  — 更新清单")


if __name__ == "__main__":
    main()
