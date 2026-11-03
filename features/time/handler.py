"""时间功能：查询当前时间、多时区时间及北京时间日期倒计时。"""

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import load_feature_config

# 无参数查询和倒计时始终使用北京时间，不依赖系统本地时区。
BEIJING = timezone(timedelta(hours=8))
WEEKDAYS = "一二三四五六日"

# IANA 时区会自动处理纽约、伦敦等地区的夏令时。
# Windows 的时区数据库由 requirements.txt 中的 tzdata 提供。
TIMEZONES = {
    "北京": "Asia/Shanghai",
    "UTC": "UTC",
    "东京": "Asia/Tokyo",
    "纽约": "America/New_York",
    "伦敦": "Europe/London",
}
TIMEZONE_ALIASES = {
    "北京时间": "北京",
    "beijing": "北京",
    "utc": "UTC",
    "gmt": "UTC",
    "tokyo": "东京",
    "new york": "纽约",
    "new_york": "纽约",
    "london": "伦敦",
}
TIMEZONE_ALIASES.update({name.lower(): label for label, name in TIMEZONES.items()})


def now_text(tz: tzinfo = BEIJING) -> str:
    """返回中文格式的当前日期时间，默认北京时间。"""
    now = datetime.now(tz)
    return f"{now.year}年{now.month}月{now.day}日 星期{WEEKDAYS[now.weekday()]} {now:%H:%M:%S}"


def _argument(text: str) -> str:
    """取命令后面的完整参数，并容忍参数两端的空白。"""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


async def cmd_time(bot, group_id, user_id, text):
    """处理 /时间 [时区]；关闭功能时，包括错误输入在内均静默。"""
    cfg = load_feature_config("time")
    if not cfg.get("enabled", False):
        return None

    argument = _argument(text)
    if not argument:
        return f"现在是 {now_text()}（北京时间）"

    label = TIMEZONE_ALIASES.get(argument.lower(), argument)
    if label not in TIMEZONES:
        available = " / ".join(TIMEZONES)
        return f"未知时区：{argument}。可用时区：{available}。用法：/时间 东京"

    try:
        tz = ZoneInfo(TIMEZONES[label])
    except ZoneInfoNotFoundError:
        return "时区数据不可用，请安装项目依赖（tzdata）后重试。"

    display_name = "北京时间" if label == "北京" else f"{label}时间"
    return f"现在是 {now_text(tz)}（{display_name}）"


async def cmd_countdown(bot, group_id, user_id, text):
    """处理 /倒计时 YYYY-MM-DD，目标为北京时间当天 00:00。"""
    cfg = load_feature_config("time")
    if not cfg.get("enabled", False):
        return None

    argument = _argument(text)
    usage = "用法：/倒计时 YYYY-MM-DD，例如 /倒计时 2026-12-31（按北京时间当天 00:00 计算）。"
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", argument):
        return f"日期格式不正确。{usage}" if argument else usage

    try:
        target_date = date.fromisoformat(argument)
    except ValueError:
        return f"日期无效。{usage}"

    target = datetime.combine(target_date, time.min, tzinfo=BEIJING)
    now = datetime.now(BEIJING)
    if target <= now:
        return f"目标时间 {argument} 00:00（北京时间）已到达或已过。"

    total_minutes = int((target - now).total_seconds() // 60)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    suffix = "（不足 1 分钟）" if total_minutes == 0 else ""
    return f"距离 {argument} 00:00（北京时间）还剩 {days} 天 {hours} 时 {minutes} 分{suffix}"


# 保留精确命令供 /help 展示，用现有正则路由接收带参数的消息。
COMMANDS = {
    "/时间": cmd_time,
    "/倒计时": cmd_countdown,
}
COMMAND_PATTERNS = {
    r"^/时间\s+.*$": cmd_time,
    r"^/倒计时\s+.*$": cmd_countdown,
}
