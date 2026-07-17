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

### 首次提交前复验

`pyproject.toml` 重新暂存后，普通 `uv run --frozen` 尝试重新创建隔离构建环境；沙箱无法访问 PyPI，因而在获取 Hatchling 时失败。该失败属于联网限制，不是测试、类型或格式失败。此前已成功执行 `uv sync --frozen`，因此使用现有锁定环境复验：

```powershell
uv run --frozen --no-sync pytest -q
uv run --frozen --no-sync mypy --strict .
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync ruff format --check .
```

结果仍为 `1 passed`、mypy 无问题、Ruff 检查通过、3 个文件已格式化。`git diff --cached --check` 退出码 0；暂存内容常见密钥/私钥模式扫描无匹配。
