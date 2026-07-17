"""Fixed, non-technical user error catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ErrorCategory, UserError

_SAFE_CODE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*\Z")


@dataclass(frozen=True, slots=True)
class _ErrorTemplate:
    what_happened: str
    data_impact: str
    next_action: str
    retryable: bool = False


_CATALOG: dict[ErrorCategory, _ErrorTemplate] = {
    ErrorCategory.VALIDATION: _ErrorTemplate(
        "输入内容无法通过验证。",
        "已有数据未受影响。",
        "请检查输入后重试。",
    ),
    ErrorCategory.NOT_FOUND: _ErrorTemplate(
        "请求的内容不存在或已不可访问。",
        "本地已有数据保持不变。",
        "请刷新状态或选择其他内容。",
    ),
    ErrorCategory.PERMISSION: _ErrorTemplate(
        "当前服务不允许执行此操作。",
        "已有数据未受影响。",
        "请检查服务权限后再试。",
    ),
    ErrorCategory.COPYRIGHT: _ErrorTemplate(
        "在线内容因版权限制不可用。",
        "歌曲和学习数据保持不变。",
        "可关联合法持有的本地 MP3 和 LRC。",
    ),
    ErrorCategory.REGION: _ErrorTemplate(
        "在线内容在当前地区不可用。",
        "歌曲和学习数据保持不变。",
        "可关联合法持有的本地 MP3 和 LRC。",
    ),
    ErrorCategory.MEMBERSHIP: _ErrorTemplate(
        "在线内容需要当前未具备的会员权限。",
        "歌曲和学习数据保持不变。",
        "可关联合法持有的本地 MP3 和 LRC。",
    ),
    ErrorCategory.AUTHENTICATION: _ErrorTemplate(
        "AI 服务未能验证当前凭据。",
        "已有解析和播放数据未受影响。",
        "请在设置中检查 API 密钥后重试。",
    ),
    ErrorCategory.QUOTA: _ErrorTemplate(
        "AI 服务当前额度或订阅不可用。",
        "已有解析和播放数据未受影响。",
        "请检查所选服务方案或额度。",
    ),
    ErrorCategory.NETWORK: _ErrorTemplate(
        "网络连接暂时不可用。",
        "已有数据未受影响。",
        "请检查网络后重试。",
        retryable=True,
    ),
    ErrorCategory.TIMEOUT: _ErrorTemplate(
        "外部服务未在规定时间内响应。",
        "已有数据未受影响。",
        "请稍后重试。",
        retryable=True,
    ),
    ErrorCategory.UNAVAILABLE: _ErrorTemplate(
        "外部服务暂时不可用。",
        "已有数据未受影响。",
        "请稍后重试。",
        retryable=True,
    ),
    ErrorCategory.INVALID_RESPONSE: _ErrorTemplate(
        "外部服务返回了无法使用的格式。",
        "旧数据保持不变且不保存不完整结果。",
        "请检查服务配置或重新发起操作。",
    ),
    ErrorCategory.STORAGE: _ErrorTemplate(
        "本地写入失败或磁盘空间不足。",
        "已有数据未受影响。",
        "请清理临时缓存并确认磁盘空间后重试。",
    ),
    ErrorCategory.INCOMPATIBLE: _ErrorTemplate(
        "备份格式与当前版本不兼容。",
        "现有数据保持不变。",
        "请选择与当前版本兼容的备份。",
    ),
    ErrorCategory.CANCELLED: _ErrorTemplate(
        "任务已取消。",
        "取消前的已有数据保持不变。",
        "需要时可重新发起操作。",
    ),
    ErrorCategory.INTERNAL: _ErrorTemplate(
        "后台任务未能完成。",
        "已有数据未受影响。",
        "请重试。若问题持续请生成诊断包。",
    ),
}


def user_error_for(category: ErrorCategory, code: str) -> UserError:
    """Build a safe error without accepting upstream response text."""

    if len(code) > 100 or _SAFE_CODE.fullmatch(code) is None:
        raise ValueError("error code must be a stable machine identifier")
    template = _CATALOG[category]
    return UserError(
        category=category,
        code=code,
        what_happened=template.what_happened,
        data_impact=template.data_impact,
        next_action=template.next_action,
        retryable=template.retryable,
    )

