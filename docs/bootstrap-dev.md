# bootstrap_dev.ps1 说明

`scripts/bootstrap_dev.ps1` 用于在新电脑、新 clone、或重建本地开发环境时，一键完成 Vox AI Input 的基础开发环境准备。

它不包含任何密钥，也不会下载本地语音模型。API key、endpoint、模型文件仍然需要在每台电脑上单独配置。

## 它会做什么

运行：

```powershell
.\scripts\bootstrap_dev.ps1
```

脚本会依次执行：

1. 切换到仓库根目录。
2. 检查 Windows Python launcher `py` 是否存在。
3. 如果 `.venv` 不存在，用 Python 3.12 创建虚拟环境。
4. 升级虚拟环境里的 `pip`。
5. 安装运行依赖：`requirements.txt`。
6. 安装开发/测试依赖：`requirements-dev.txt`。
7. 如果 `config.yaml` 不存在，从 `config.example.yaml` 复制一份。
8. 如果 `models/` 不存在，创建目录。
9. 默认执行编译检查和测试：

```powershell
python -m compileall -q run.py src tests
python -m pytest -q
```

## 常用参数

只安装环境，不跑编译和测试：

```powershell
.\scripts\bootstrap_dev.ps1 -SkipVerify
```

只安装运行依赖，不安装测试依赖：

```powershell
.\scripts\bootstrap_dev.ps1 -SkipDevDependencies
```

指定 Python 版本：

```powershell
.\scripts\bootstrap_dev.ps1 -PythonVersion 3.12
```

## 什么时候用

- 新电脑第一次 clone 项目后。
- `.venv` 被删掉或损坏后。
- 依赖升级后想重新安装一遍。
- 让一个没有历史 session 的 Codex 先把开发环境准备好。

## 什么时候不用

- 日常已经有 `.venv` 且依赖没有变化时，不需要每次运行。
- 只想启动软件时，直接激活虚拟环境后运行 `python run.py`。
- 只想修改文档时，不需要完整 bootstrap。

## 让 Codex 先执行它

仓库根目录的 `AGENTS.md` 已经写入 `Fresh Clone Bootstrap` 规则。新的 Codex session 进入项目后，会看到这个规则。

完整入口提示词见 `docs/codex-entry-prompts.md`。

新电脑 clone 后可以这样启动 Codex：

```powershell
codex "这是一个刚 clone 的 vox-ai-input 仓库。请先按 AGENTS.md 的 Fresh Clone Bootstrap 初始化项目，然后总结结果。"
```

或者用非交互模式：

```powershell
codex exec "这是一个刚 clone 的 vox-ai-input 仓库。请先按 AGENTS.md 的 Fresh Clone Bootstrap 初始化项目，然后总结结果。"
```

注意：不要把仓库配置成 `git clone` 完成后无条件自动执行脚本。自动运行刚下载的仓库代码是不安全的。更好的方式是让 Codex 读取 `AGENTS.md` 后执行，并在需要时由你批准。

## 本机配置

脚本只会在 `config.yaml` 不存在时创建它，不会覆盖已有配置。

你需要自己填写：

- `llm_profiles.default.endpoint`
- `llm_profiles.default.api_key`
- `llm_profiles.default.model`
- 本机热键和悬浮按钮偏好
- 本地 STT 模型下载状态

`config.yaml` 已被 `.gitignore` 忽略，不应该提交。
