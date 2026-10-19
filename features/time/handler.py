"""时间功能：群里发 /时间，回复当前日期时间（北京时间，中文格式）。

回复示例：现在是 2026年10月19日 星期一 16:08:05（北京时间）
"""

from datetime import datetime, timedelta, timezone

from config import load_feature_config

# 北京时间（UTC+8）。用固定偏移而不是系统本地时区，
# 这样无论机器人跑在什么时区的机器上，回复的时间都一致。
BEIJING = timezone(timedelta(hours=8))

# datetime.weekday() 返回 0~6，对应星期一到星期日
WEEKDAYS = "一二三四五六日"


def now_text() -> str:
    """返回中文格式的当前日期时间，例如：2026年10月19日 星期一 16:08:05。"""
    now = datetime.now(BEIJING)
    return f"{now.year}年{now.month}月{now.day}日 星期{WEEKDAYS[now.weekday()]} {now:%H:%M:%S}"


async def cmd_time(bot, group_id, user_id, text):
    """处理 /时间：启用时回复当前日期时间，未启用时静默。"""
    cfg = load_feature_config("time")
    if not cfg.get("enabled", False):
        return None

    return f"现在是 {now_text()}（北京时间）"


# ★ 必须导出 COMMANDS，机器人才能发现这个命令
COMMANDS = {
    "/时间": cmd_time,
}
