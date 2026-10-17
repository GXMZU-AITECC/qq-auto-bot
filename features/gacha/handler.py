"""抽卡功能：群里发 /抽卡，随机抽出一张卡并回复卡名与稀有度。

稀有度：白 / 绿 / 蓝 / 紫 / 金，越稀有概率越低。
"""

import random

from config import load_feature_config

# 稀有度权重：数字越大越容易抽到（总和 100）
RARITY_WEIGHTS = {
    "白": 50,
    "绿": 25,
    "蓝": 15,
    "紫": 8,
    "金": 2,
}

# 每个稀有度对应的卡池：越稀有越贵、越难拿到
CARD_POOL = {
    "白": ["烧掉的电源", "断了的天线", "滑丝的螺丝", "没标注的数据集"],
    "绿": ["舵机", "蓝牙模块", "如意点档三重抹茶拿破仑酥", "别人训好的模型"],
    "蓝": ["激光雷达", "机械臂", "深度相机", "跑得动模型的显卡"],
    "紫": ["宇树 G1", "云卓无人机", "3D 打印机", "GPU 服务器"],
    "金": ["不宕机的服务器", "秒批的经费申请", "无限 token 额度", "免费的正版软件"],
}


def draw_card() -> tuple[str, str]:
    """按权重抽一个稀有度，再从该稀有度的卡池里随机取一张，返回 (卡名, 稀有度)。"""
    rarities = list(RARITY_WEIGHTS)
    weights = [RARITY_WEIGHTS[r] for r in rarities]
    rarity = random.choices(rarities, weights=weights, k=1)[0]
    return random.choice(CARD_POOL[rarity]), rarity


async def cmd_draw(bot, group_id, user_id, text):
    """处理 /抽卡：启用时抽一张卡，未启用时静默。"""
    cfg = load_feature_config("gacha")
    if not cfg.get("enabled", False):
        return None

    name, rarity = draw_card()
    return f"🎴 抽卡结果：【{rarity}】{name}"


# ★ 必须导出 COMMANDS，机器人才能发现这个命令
COMMANDS = {
    "/抽卡": cmd_draw,
}
