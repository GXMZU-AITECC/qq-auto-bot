# features/ping/handler.py
# /ping 命令（新人任务 #17）：群里发 /ping，机器人回 pong 🏓


async def cmd_ping(bot, group_id, user_id, text):
    """收到 /ping 时回复 pong 🏓"""
    return "pong 🏓"


# 机器人启动时自动发现的命令表（不改 main.py）
COMMANDS = {
    "/ping": cmd_ping,
}
