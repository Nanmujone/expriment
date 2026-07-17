# 英文歌曲歌词学习播放器

这是一个面向 Windows 10/11 的个人英语学习桌面应用。第一版目标是导入公开歌单、播放合法可用的在线或本地音频、同步显示歌词，并在用户主动操作时提供 AI 翻译、语境解析、问答和词句收藏。

## 当前状态

项目处于第一版开发阶段。需求基线见 `需求/requirements.md`，架构基线见 `doc/high-level-design.md`，任务与真实进度见 `拆分/tasks/`。任何未在进度文件中勾选并附验证证据的功能都不应视为已完成。

## 开发环境

- Windows 10/11 x64
- Python 3.12
- `uv`
- Node.js LTS

安装依赖并运行质量门：

```powershell
uv sync --frozen
uv run pytest -q
uv run mypy --strict .
uv run ruff check .
uv run ruff format --check .
```

API 密钥必须通过应用写入 Windows Credential Manager。不要把密钥、Cookie、数据库、备份、日志、用户媒体或用户歌词提交到 Git。
