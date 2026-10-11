"""彩蛋功能：群里发「我们会赢吗」，机器人回一句应援语。

本文件同时充当**范例**，展示一个标准功能的三个部分：
  1. `__init__.py` —— 让目录被识别为一个包（内容留空即可）
  2. `handler.py`  —— 本文件：处理函数 + 导出 COMMANDS
  3. `configs/easteregg.yaml` —— 功能开关等配置

照抄这个结构就能加自己的功能，机器人启动时会自动发现，不用改 main.py。
"""

from config import load_feature_config

# 机器人要回复的内容（多行原样发送）
REPLY = """Maybe not today,
maybe not tomorrow,
but just one day,
we are champion!!!"""


async def cmd_champion(bot, group_id, user_id, text):
    """处理「我们会赢吗」：启用时返回应援语。

    bot       → 发消息、查信息全靠它
    group_id  → 群号
    user_id   → 发消息的人的 QQ 号
    text      → 群友发的原始消息全文（这里用不到）
    """
    # 读 configs/easteregg.yaml，未启用就静默不回
    cfg = load_feature_config("easteregg")
    if not cfg.get("enabled", False):
        return None

    return REPLY


# ★ 必须导出 COMMANDS，机器人才能发现这个命令
# 键是"精确匹配的整条消息"，所以群友发「我们会赢吗」才触发
COMMANDS = {
    "我们会赢吗": cmd_champion,
}
