"""早安模糊触发功能。

对以「早安」开头的消息回复一句问候，使用 COMMAND_PATTERNS 正则匹配。
"""

async def cmd_morning(bot, group_id, user_id, text):
    """Reply to morning greetings."""
    return "早安！今天也要开心哦～"

# 模糊匹配：以「早安」开头的消息（全文匹配，允许后续字符）
COMMAND_PATTERNS = {
    r"^早安.*": cmd_morning,
}
