"""cron 表达式解析（包装 croniter）。

只支持 5 段标准写法：分 时 日 月 周。
"""

from datetime import datetime

from croniter import croniter

_FIELDS = 5


def _split(expr: str) -> list[str] | None:
    parts = expr.split()
    return parts if len(parts) == _FIELDS else None


def is_valid(expr: str) -> bool:
    if _split(expr) is None:
        return False
    try:
        croniter(expr, datetime.now())
        return True
    except (ValueError, KeyError, TypeError):
        return False


def matches(expr: str, dt: datetime) -> bool:
    """完整匹配（分 时 日 月 周）；非法表达式返回 False。"""
    if _split(expr) is None:
        return False
    try:
        return bool(croniter.match(expr, dt))
    except (ValueError, KeyError, TypeError):
        return False


def matches_time(expr: str, dt: datetime) -> bool:
    """只匹配分/时两字段（忽略日/月/周）；非法表达式返回 False。"""
    parts = _split(expr)
    if parts is None:
        return False
    minute, hour = parts[0], parts[1]
    try:
        return bool(
            croniter.match(f"{minute} * * * *", dt)
            and croniter.match(f"* {hour} * * *", dt)
        )
    except (ValueError, KeyError, TypeError):
        return False
