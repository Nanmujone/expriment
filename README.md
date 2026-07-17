# 英文歌曲歌词学习播放器

这是一个面向 Windows 10/11 的个人英语学习桌面应用。当前精简首版支持只读打开本地 MP3、自动载入同名 LRC、同步歌词，以及由用户主动确认后调用其配置的 OpenAI Chat Completions 兼容服务解析歌词。

## 当前状态

网易云在线验证门当前为 `PARTIAL_OFFLINE`，因此在线导入、播放和歌词入口保持禁用，首版不携带 Node.js。需求基线见 `需求/requirements.md`，架构基线见 `doc/high-level-design.md`，任务与真实进度见 `拆分/tasks/`。任何未在进度文件中勾选并附验证证据的功能都不应视为已完成。

## 开发环境

- Windows 10/11 x64
- Python 3.12
- `uv`
- Node.js 仅供未来 `ONLINE_GATE_PASSED` 构建使用；当前首版不需要

安装依赖并运行质量门：

```powershell
uv sync --frozen
uv run pytest -q
uv run mypy --strict .
uv run ruff check .
uv run ruff format --check .
```

直接从源码启动：

```powershell
.\.venv\Scripts\python.exe -m english_player
```

当前开发电脑也可以直接双击仓库根目录的 `run-first-release.cmd`，它使用项目内已经配置好的 Python 环境启动，不修改系统 Python。

生成精简便携构建：

```powershell
.\scripts\build-first-release.ps1
```

构建输出位于 `dist\EnglishSongLearningPlayer\`。当前未签名 EXE 在启用了严格 Windows Application Control 的电脑上可能被阻止；该情况需要可信代码签名，不能通过关闭系统安全策略规避。

API 密钥必须通过应用写入 Windows Credential Manager。不要把密钥、Cookie、数据库、备份、日志、用户媒体或用户歌词提交到 Git。
