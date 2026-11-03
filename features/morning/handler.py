"""早安：群里有人发以「早安」开头的消息时，回一句问候。"""

from config import load_feature_config

GREETING = "早安呀！今天也要充满活力哦~ ☀️"


async def cmd_morning(bot, group_id, user_id, text):
    """处理以「早安」开头的消息：未启用时静默，启用时回问候。"""
    cfg = load_feature_config("morning")
    if not cfg or not cfg.get("enabled", False):
        return None

    return GREETING


# 注意：features.dispatch() 用的是 fullmatch，不是 search。
# 所以「模糊触发」必须写成 ^早安.*$；只写 ^早安 的话，
# 只有整条消息恰好是「早安」才会触发，「早安各位」会被漏掉。
COMMAND_PATTERNS = {
    r"^早安.*$": cmd_morning,
}

PATTERN_HELP = {
    r"^早安.*$": "早安（发「早安…」即触发）",
}
