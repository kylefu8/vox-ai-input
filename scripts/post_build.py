"""
构建后处理脚本

在 PyInstaller --onedir 构建完成后运行，生成增量更新包：
1. 打包源代码文件 + 资源为 app-update.zip
2. 生成 update-manifest.json（版本号 + SHA256）

增量更新原理：
    PyInstaller --onedir 模式下，_internal/ 中的 PYZ 存档包含所有 .pyc。
    增量更新时，直接用新的 PYZ 和相关文件覆盖 _internal/ 即可。
    所以 app-update.zip 包含 _internal/ 中除 Python 运行时和第三方库之外的文件。

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

# 属于"我们的代码"的文件/目录
# 在 PyInstaller --onedir 中，这些文件在 _internal/ 下
# PYZ-00.pyz 包含了所有编译过的 .py 模块
OUR_PATTERNS = [
    # PyInstaller 核心产物（包含编译的 Python 代码）
    "base_library.zip",
    # 数据文件（assets/ 和配置模板）
    "assets/",
    "config.example.yaml",
]


def _get_version():
    """从 run.py 读取版本号。"""
    run_py = PROJECT_ROOT / "run.py"
    for line in run_py.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip('"').strip("'")
    return "0.0.0"


def _sha256_file(path):
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_update_files():
    """
    收集增量更新包的文件。

    包含 _internal/ 中与我们的代码相关的文件。
    排除 Python 运行时 DLL 和第三方 .pyd 文件（这些很少变化且体积大）。

    Returns:
        list[tuple[Path, str]]: [(绝对路径, zip内相对路径), ...]
    """
    files = []

    if not INTERNAL_DIR.exists():
        print(f"警告: _internal 目录不存在: {INTERNAL_DIR}")
        return files

    # 收集 assets/ 目录
    assets_dir = INTERNAL_DIR / "assets"
    if assets_dir.exists():
        for f in assets_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(INTERNAL_DIR)
                files.append((f, str(rel)))

    # 收集 config.example.yaml
    cfg = INTERNAL_DIR / "config.example.yaml"
    if cfg.exists():
        files.append((cfg, "config.example.yaml"))

    # 收集 PYZ 存档（包含所有编译的 Python 模块）
    for pyz in INTERNAL_DIR.glob("*.pyz"):
        files.append((pyz, pyz.name))

    # 收集 base_library.zip
    base_lib = INTERNAL_DIR / "base_library.zip"
    if base_lib.exists():
        files.append((base_lib, "base_library.zip"))

    # 如果有独立的 src/ 目录（某些 PyInstaller 配置会展开）
    src_dir = INTERNAL_DIR / "src"
    if src_dir.exists():
        for f in src_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(INTERNAL_DIR)
                files.append((f, str(rel)))

    return files


def main():
    """主函数。"""
    print("=" * 50)
    print("Vox AI Input — 构建后处理")
    print("=" * 50)

    if not DIST_DIR.exists():
        print(f"错误: 构建目录不存在: {DIST_DIR}")
        print("请先运行: pyinstaller build.spec --clean --noconfirm")
        sys.exit(1)

    version = _get_version()
    print(f"版本: v{version}")

    # 创建 release 目录
    RELEASE_DIR.mkdir(exist_ok=True)

    # 收集文件
    update_files = _collect_update_files()

    if not update_files:
        print("警告: 未找到增量更新文件，仅生成清单")
        # 即使没有增量文件也不报错，CI 可以只发布安装包
        manifest = {"version": version, "assets": {}, "files": {}}
        manifest_path = RELEASE_DIR / "update-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"清单: {manifest_path}")
        return

    print(f"增量更新文件数: {len(update_files)}")
    total_size = 0
    for abs_path, rel_path in update_files:
        size = abs_path.stat().st_size
        total_size += size
        print(f"  {rel_path}  ({size // 1024} KB)")
    print(f"  总计: {total_size // 1024} KB（压缩前）")

    # 生成 app-update.zip
    zip_path = RELEASE_DIR / "app-update.zip"
    print(f"\n生成增量更新包: {zip_path}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for abs_path, rel_path in update_files:
            zf.write(abs_path, rel_path)

    zip_size = zip_path.stat().st_size
    print(f"  压缩后: {zip_size // 1024} KB")

    # 生成 update-manifest.json
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

    for abs_path, rel_path in update_files:
        manifest["files"][rel_path] = {
            "size": abs_path.stat().st_size,
            "sha256": _sha256_file(abs_path),
        }

    manifest_path = RELEASE_DIR / "update-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"清单: {manifest_path}")

    # 复制 config.example.yaml
    example_cfg = PROJECT_ROOT / "config.example.yaml"
    if example_cfg.exists():
        shutil.copy2(example_cfg, RELEASE_DIR / "config.example.yaml")

    print(f"\n完成！产物在 {RELEASE_DIR}/")


if __name__ == "__main__":
    main()
