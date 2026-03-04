"""
一键升级模块

通过 GitHub Releases API 检查版本更新，支持两种更新模式：

1. 增量更新（优先）：下载 app-update.zip（~100KB），只替换应用代码
2. 全量更新（回退）：下载安装包 VoxAIInput-Setup-*.exe 并运行

流程：
1. checkForUpdates() — 查询 GitHub 最新 Release + update-manifest.json
2. downloadUpdate() — 下载增量包或安装包
3. applyUpdate() — 解压覆盖 _internal/ 或运行安装包，然后重启
"""

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

from src.logger import setup_logger

log = setup_logger(__name__)

# GitHub 仓库信息
REPO_OWNER = "kylefu8"
REPO_NAME = "vox-ai-input"
RELEASES_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

# Release 中的资产文件名
APP_UPDATE_ZIP = "app-update.zip"
UPDATE_MANIFEST = "update-manifest.json"
SETUP_EXE_PREFIX = "VoxAIInput-Setup-"


def _get_current_version():
    """获取当前版本号。"""
    try:
        from run import __version__
        return __version__
    except Exception:
        return "0.0.0"


def _compare_versions(v1, v2):
    """
    比较两个语义化版本。

    Returns:
        int: 1 if v1 > v2, -1 if v1 < v2, 0 if equal
    """
    def parse(v):
        return [int(x) for x in v.lstrip("v").split(".")[:3]]

    try:
        a, b = parse(v1), parse(v2)
        while len(a) < 3:
            a.append(0)
        while len(b) < 3:
            b.append(0)
        return (a > b) - (a < b)
    except Exception:
        return 0


def _is_frozen():
    """是否是 PyInstaller 打包模式。"""
    return getattr(sys, "frozen", False)


def _get_exe_path():
    """获取当前 exe 的路径。"""
    if _is_frozen():
        return Path(sys.executable)
    return None


def _get_internal_dir():
    """获取 _internal 目录。"""
    if _is_frozen():
        return Path(sys._MEIPASS)
    return None


def _sha256_file(path):
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data):
    """计算字节数据 SHA256。"""
    return hashlib.sha256(data).hexdigest()


def _http_get(url, timeout=30):
    """发起 HTTP GET 请求，返回响应数据。"""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"VoxAIInput/{_get_current_version()}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_download(url, on_progress=None, timeout=300):
    """
    下载文件，支持进度回调。

    Args:
        url: 下载链接
        on_progress: callback(downloaded, total)
        timeout: 超时秒数

    Returns:
        bytes: 下载的数据
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"VoxAIInput/{_get_current_version()}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunks = []

        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if on_progress and total > 0:
                on_progress(downloaded, total)

    return b"".join(chunks)


class Updater:
    """
    版本更新管理器。

    状态机：
        idle → checking → available / up_to_date / error
        available → downloading → ready / error
        ready → (apply and restart)

    更新模式：
        lightweight: 仅替换 _internal/src/ 等应用文件（~100KB）
        full: 运行安装包（~30MB）
    """

    def __init__(self):
        self.state = "idle"
        self.current_version = _get_current_version()
        self.latest_version = None
        self.release_url = None
        self.update_mode = None       # "lightweight" | "full" | None
        self.download_url = None
        self.download_size = 0
        self.download_progress = 0    # 0-100
        self.error_message = ""
        self._manifest = None         # update-manifest.json 内容
        self._temp_file = None        # 下载的临时文件
        self._release_data = None     # GitHub release JSON
        self._on_state_change = None

    def set_callback(self, callback):
        """设置状态变化回调。"""
        self._on_state_change = callback

    def _notify(self):
        """通知状态变化。"""
        if self._on_state_change:
            try:
                self._on_state_change(self)
            except Exception:
                pass

    # ==================== 检查更新 ====================

    def check_for_updates(self, background=False):
        """检查是否有新版本。"""
        if background:
            threading.Thread(target=self._do_check, daemon=True).start()
        else:
            self._do_check()

    def _do_check(self):
        """执行版本检查。"""
        self.state = "checking"
        self._notify()

        try:
            data = json.loads(_http_get(RELEASES_API).decode("utf-8"))
            self._release_data = data

            tag = data.get("tag_name", "")
            self.latest_version = tag.lstrip("v")
            self.release_url = data.get("html_url", "")

            if _compare_versions(self.latest_version, self.current_version) <= 0:
                self.state = "up_to_date"
                log.info("已是最新版本: v%s", self.current_version)
                self._notify()
                return

            log.info("发现新版本: v%s（当前: v%s）", self.latest_version, self.current_version)

            # 判断更新模式
            self._determine_update_mode(data.get("assets", []))

            self.state = "available"

        except urllib.error.URLError as e:
            self.state = "error"
            self.error_message = f"网络错误: {e.reason}"
            log.warning("检查更新失败: %s", e)
        except Exception as e:
            self.state = "error"
            self.error_message = str(e)
            log.warning("检查更新失败: %s", e)

        self._notify()

    def _determine_update_mode(self, assets):
        """
        根据 release assets 判断使用增量还是全量更新。

        优先增量（如果有 app-update.zip + manifest），否则全量。
        """
        asset_map = {a["name"]: a for a in assets}

        # 查找增量更新资产
        has_app_zip = APP_UPDATE_ZIP in asset_map
        has_manifest = UPDATE_MANIFEST in asset_map

        # 查找全量安装包
        setup_asset = None
        for name, asset in asset_map.items():
            if name.startswith(SETUP_EXE_PREFIX) and name.endswith(".exe"):
                setup_asset = asset
                break

        if _is_frozen() and has_app_zip and has_manifest:
            # 尝试增量更新
            try:
                manifest_data = _http_get(asset_map[UPDATE_MANIFEST]["browser_download_url"])
                self._manifest = json.loads(manifest_data.decode("utf-8"))

                self.update_mode = "lightweight"
                self.download_url = asset_map[APP_UPDATE_ZIP]["browser_download_url"]
                self.download_size = asset_map[APP_UPDATE_ZIP].get("size", 0)
                log.info("增量更新可用: app-update.zip (%d KB)",
                         self.download_size // 1024)
                return
            except Exception as e:
                log.warning("增量更新清单获取失败，回退到全量: %s", e)

        if setup_asset:
            self.update_mode = "full"
            self.download_url = setup_asset["browser_download_url"]
            self.download_size = setup_asset.get("size", 0)
            log.info("全量更新: %s (%d MB)",
                     setup_asset["name"], self.download_size // (1024 * 1024))
        elif APP_UPDATE_ZIP in asset_map and not _is_frozen():
            # 源码模式
            self.update_mode = "full"
            self.download_url = None
            log.info("源码模式，请手动 git pull")
        else:
            self.update_mode = "full"
            self.download_url = None
            log.warning("Release 中没有找到可下载的更新文件")

    # ==================== 下载更新 ====================

    def download_update(self, background=True):
        """下载更新包。"""
        if not self.download_url:
            self.state = "error"
            self.error_message = "没有可下载的更新文件"
            self._notify()
            return

        if background:
            threading.Thread(target=self._do_download, daemon=True).start()
        else:
            self._do_download()

    def _do_download(self):
        """执行下载。"""
        self.state = "downloading"
        self.download_progress = 0
        self._notify()

        try:
            def on_progress(downloaded, total):
                self.download_progress = int(downloaded * 100 / total) if total > 0 else 0
                self._notify()

            data = _http_download(self.download_url, on_progress=on_progress)

            # SHA256 校验（增量更新时）
            if self.update_mode == "lightweight" and self._manifest:
                expected_hash = self._manifest.get("assets", {}).get(
                    APP_UPDATE_ZIP, {}
                ).get("sha256", "")
                actual_hash = _sha256_bytes(data)
                if expected_hash and actual_hash != expected_hash:
                    raise ValueError(
                        f"SHA256 校验失败！\n"
                        f"  期望: {expected_hash[:16]}...\n"
                        f"  实际: {actual_hash[:16]}..."
                    )
                log.info("SHA256 校验通过")

            # 保存到临时文件
            temp_dir = Path(tempfile.gettempdir()) / "vox-ai-input-update"
            temp_dir.mkdir(exist_ok=True)

            if self.update_mode == "lightweight":
                temp_file = temp_dir / APP_UPDATE_ZIP
            else:
                # 全量安装包
                temp_file = temp_dir / f"VoxAIInput-Setup-{self.latest_version}.exe"

            temp_file.write_bytes(data)
            self._temp_file = temp_file

            self.state = "ready"
            self.download_progress = 100
            size_mb = len(data) / (1024 * 1024)
            log.info("下载完成: %s (%.1f MB)", temp_file.name, size_mb)

        except Exception as e:
            self.state = "error"
            self.error_message = f"下载失败: {e}"
            log.error("下载更新失败: %s", e)

        self._notify()

    # ==================== 应用更新 ====================

    def apply_update(self):
        """
        应用更新并重启。

        增量模式：解压 zip → 覆盖 _internal/ → bat 脚本重启
        全量模式：运行安装包（/SILENT 静默安装）→ 安装完自动启动
        """
        if not self._temp_file or not self._temp_file.exists():
            log.error("更新文件不存在")
            return False

        if self.update_mode == "lightweight":
            return self._apply_lightweight()
        else:
            return self._apply_full()

    def _apply_lightweight(self):
        """增量更新：解压 app-update.zip 并重启。"""
        internal_dir = _get_internal_dir()
        exe_path = _get_exe_path()

        if not internal_dir or not exe_path:
            log.error("无法确定安装路径")
            return False

        zip_path = self._temp_file
        bat_path = self._temp_file.parent / "_update_lightweight.bat"

        # bat 脚本：等待旧进程退出 → 解压覆盖 → 重启 → 清理
        bat_content = f"""@echo off
chcp 65001 >nul 2>&1
echo Vox AI Input - 增量更新中...
echo 等待旧进程退出...
ping 127.0.0.1 -n 3 >nul 2>&1

echo 解压更新文件...
powershell -Command "Expand-Archive -Path '{zip_path}' -DestinationPath '{internal_dir}' -Force" 2>nul
if errorlevel 1 (
    echo 解压失败，重试...
    ping 127.0.0.1 -n 2 >nul 2>&1
    powershell -Command "Expand-Archive -Path '{zip_path}' -DestinationPath '{internal_dir}' -Force" 2>nul
)

echo 启动新版本...
start "" "{exe_path}"

echo 清理临时文件...
del /q "{zip_path}" >nul 2>&1
del /q "%~f0" >nul 2>&1
"""
        bat_path.write_text(bat_content, encoding="utf-8")

        log.info("增量更新脚本已生成，即将重启...")

        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )

        return True

    def _apply_full(self):
        """全量更新：运行安装包。"""
        setup_exe = self._temp_file

        if not setup_exe or not setup_exe.exists():
            log.error("安装包不存在")
            return False

        log.info("启动安装包: %s", setup_exe)

        # /SILENT 静默安装，/CLOSEAPPLICATIONS 关闭正在运行的实例
        subprocess.Popen(
            [str(setup_exe), "/SILENT", "/CLOSEAPPLICATIONS"],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )

        return True

    def open_release_page(self):
        """在浏览器中打开 GitHub Release 页面。"""
        url = self.release_url or f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases"
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            log.error("打开浏览器失败: %s", e)
