# features/fortune/handler.py
# /今日运势 命令（新人任务 #22）：从一组固定文案里随机挑一句回复

import random

from config import load_feature_config

# 固定运势文案池
FORTUNES = [
    "🔮 今日运势：大吉。宜摸鱼，忌开会。",
    "🔮 今日运势：大吉。你等的快递今天必到。",
    "🔮 今日运势：中吉。午饭会有好事发生。",
    "🔮 今日运势：中吉。今天适合跟产品经理说“可以做”。",
    "🔮 今日运势：小吉。今日宜准时下班。",
    "🔮 今日运势：平。今天平安无事就是最大的胜利。",
    "🔮 今日运势：小凶。忌立flag，宜先干活后许愿。",
]


async def cmd_fortune(bot, group_id, user_id, text):
    # 未启用时保持静默（读 configs/fortune.yaml 的 enabled 开关）
    cfg = load_feature_config("fortune")
    if not cfg.get("enabled", False):
        return None

    return random.choice(FORTUNES)


# 机器人启动时自动发现的命令表（不改 main.py）
COMMANDS = {
    "/今日运势": cmd_fortune,
}
