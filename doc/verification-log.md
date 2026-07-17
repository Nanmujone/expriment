# 验证日志

本文件只记录实际执行过的命令和结果。计划、推测或 Agent 自述不能替代新鲜命令证据。

## 2026-07-17 工程初始化

### 环境

| 项目 | 实际结果 |
| --- | --- |
| 工作区 | `C:\Users\liush\Desktop\expriments` |
| Python（项目） | CPython 3.12.13，工作区隔离安装 |
| Python（系统现有） | CPython 3.14.6；项目不使用 |
| uv | 0.11.29 |
| Node.js | v24.18.0 LTS（Krypton） |
| Git | 2.55.0.windows.2 |
| VS Code | 1.129.0 x64 |
| GitHub CLI | 未安装；已有仓库推送不依赖 `gh` |

项目解释器：`C:\Users\liush\Desktop\expriments\.venv\Scripts\python.exe`。

### Git 与敏感信息

- 空 `.git` 目录已通过 `git init -b main` 修复为有效仓库。
- `origin` 已配置为 `https://github.com/Nanmujone/expriment.git`。
- `GCM_INTERACTIVE=Never git ls-remote origin` 退出码为 0 且无引用，说明远程可访问并且当时为空仓库。
- 在首次提交前创建 `.gitignore`，覆盖虚拟环境、工具缓存、密钥、Cookie、数据库、备份、日志、诊断、用户媒体、用户歌词、IDE 本地状态和 worktree。
- 初始化前的文件名、常见凭据模式和私钥头扫描没有发现匹配；首次提交前仍需对实际暂存内容再次扫描。

### 依赖

```powershell
uv lock --python 3.12
uv sync --frozen --python 3.12
```

- 锁定解析：55 个包。
- 同步结果：Python 3.12.13 虚拟环境创建成功，49 个包安装成功。

### 基线质量门

第一次格式检查发现 `src/english_player/__init__.py` 和 `tests/conftest.py` 需要格式化；使用同一锁定 Ruff 版本格式化后重新执行全部质量门：

```powershell
uv run --frozen pytest -q
uv run --frozen mypy --strict .
uv run --frozen ruff check .
uv run --frozen ruff format --check .
```

最终结果：

- pytest：`1 passed`；
- mypy strict：`Success: no issues found in 3 source files`；
- Ruff check：`All checks passed!`；
- Ruff format check：`3 files already formatted`。

该结果只证明空工程基线可用，不代表任何业务模块已完成。

## 2026-07-17 阶段 0 合并验证

后台任务、持久化迁移和网易云可行性验证分支合并后，首次全量 pytest 收集发现 `tests/tasks/test_models.py` 与 `tests/persistence/test_models.py` 同名冲突。根因是 pytest 默认导入模式把不同目录下的同名测试模块放入同一顶层命名空间；在 `pyproject.toml` 固定 `--import-mode=importlib` 后重新执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mypy --strict src tools
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

结果：pytest `122 passed in 4.09s`；mypy strict 检查 25 个源文件无错误；Ruff check 通过；44 个文件格式正确；`git diff --check` 退出码 0。

网易云验证证据见 `doc/verification/netease-gate-2026-07-17.md`，门状态为 `PARTIAL_OFFLINE`。用户确认首版接受该状态，并要求精简、尽快交付；因此当前首版排除 Node.js 和网易云适配层，继续本地 MP3/LRC 与 AI 主链路。

## 2026-07-17 精简首版候选

本地媒体、歌词、播放器、Qt 界面和 AI Chat Completions 兼容适配器加入后，执行全量质量门：pytest `147 passed in 4.75s`；mypy strict 检查 45 个源文件无错误；Ruff 检查通过；72 个文件格式正确；`git diff --check` 退出码 0。

`scripts/build-first-release.ps1` 使用 PyInstaller 6.21.0 生成 `PARTIAL_OFFLINE` onedir 构建，输出目录大小为 147 MiB，递归检查未发现 `node.exe`。

打包 EXE 启动烟雾测试未通过：本机 Windows Application Control 策略阻止未签名 PyInstaller EXE 启动。最初的临时 PowerShell 命令没有把 `Start-Process` 的非终止错误转成失败，因而错误打印成功提示；已新增 `$ErrorActionPreference = "Stop"` 的 `scripts/smoke-packaged-app.ps1` 防止假阳性。源码运行和 pytest-qt 界面测试通过，但真实打包 EXE 启动项保持未验证，发布前需要可信代码签名或允许该发布者的受控测试环境。

便携 ZIP：`dist/EnglishSongLearningPlayer-0.1.0-partial-offline-win64.zip`，61.3 MiB，SHA-256 `262A119CBE3BA6A077FA38C92E8891D4E38F6106CFE5A3E168DE81AE3A6CCB80`。该文件因包含未签名 EXE，当前只作为候选产物，不标记正式发布。

为区分程序错误与打包策略阻止，使用项目内 `.venv\Scripts\pythonw.exe -m english_player` 启动同一桌面应用；进程成功运行 3 秒并通过主窗口受控关闭。因此当前代码和项目内运行环境可用，阻塞范围限定为未签名打包 EXE。仓库根目录提供 `run-first-release.cmd` 作为当前开发电脑的直接启动入口。

### 首次提交前复验

`pyproject.toml` 重新暂存后，普通 `uv run --frozen` 尝试重新创建隔离构建环境；沙箱无法访问 PyPI，因而在获取 Hatchling 时失败。该失败属于联网限制，不是测试、类型或格式失败。此前已成功执行 `uv sync --frozen`，因此使用现有锁定环境复验：

```powershell
uv run --frozen --no-sync pytest -q
uv run --frozen --no-sync mypy --strict .
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync ruff format --check .
```

结果仍为 `1 passed`、mypy 无问题、Ruff 检查通过、3 个文件已格式化。`git diff --cached --check` 退出码 0；暂存内容常见密钥/私钥模式扫描无匹配。
