"""/猜拳 命令：跟机器人玩石头剪刀布（新人任务 #18）。

用法：
  /猜拳 石头
  /猜拳 剪刀
  /猜拳 布
"""

import random

from config import load_feature_config

CHOICES = ("石头", "剪刀", "布")

# 胜负表：键 克 值（石头砸剪刀、剪刀剪布、布包石头）
BEATS = {"石头": "剪刀", "剪刀": "布", "布": "石头"}

USAGE = "用法：/猜拳 石头 | /猜拳 剪刀 | /猜拳 布"


async def cmd_rps(bot, group_id, user_id, text):
    """处理 /猜拳 xxx：合法就出拳判胜负，非法给用法提示。"""
    cfg = load_feature_config("rps")
    if not cfg.get("enabled", False):
        return None

    # 从 "/猜拳 石头" 里取出玩家出的拳（没带参数就是空字符串）
    parts = text.split(maxsplit=1)
    player = parts[1].strip() if len(parts) > 1 else ""

    # 参数不合法（包括没带参数）时给出用法
    if player not in CHOICES:
        return USAGE

    bot_choice = random.choice(CHOICES)

    if player == bot_choice:
        result = "平局"
    elif BEATS[player] == bot_choice:
        result = "你赢了"
    else:
        result = "你输了"

    return f"你出 {player}，我出 {bot_choice} —— {result}"


# ★ 带参数的命令必须用正则匹配（COMMANDS 只认整条消息完全相等）
COMMAND_PATTERNS = {
    r"^/猜拳(?:\s+.*)?$": cmd_rps,
}
