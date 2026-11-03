"""抽卡功能：群里发 /抽卡 单抽，发 /抽卡 十连 抽十张并保底。

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

# 十连保底：这十张里至少要有一张属于这几种稀有度
GUARANTEE_RARITIES = ("蓝", "紫", "金")

# 十连一次抽几张
TEN_PULL_COUNT = 10

# 参数不认识时的用法提示
USAGE = "📖 用法：/抽卡 单抽 ｜ /抽卡 十连"


def draw_card() -> tuple[str, str]:
    """按权重抽一个稀有度，再从该稀有度的卡池里随机取一张，返回 (卡名, 稀有度)。"""
    rarities = list(RARITY_WEIGHTS)
    weights = [RARITY_WEIGHTS[r] for r in rarities]
    rarity = random.choices(rarities, weights=weights, k=1)[0]
    return random.choice(CARD_POOL[rarity]), rarity


def draw_ten() -> list[tuple[str, str, bool]]:
    """抽十张，保证至少一张蓝及以上。

    返回 [(卡名, 稀有度, 是否保底), ...]，共 10 条。
    若十张全是白/绿，则把最后一张换成按权重抽出的蓝/紫/金，并标记为保底。
    """
    cards: list[tuple[str, str, bool]] = []
    for _ in range(TEN_PULL_COUNT):
        name, rarity = draw_card()
        cards.append((name, rarity, False))

    if any(rarity in GUARANTEE_RARITIES for _, rarity, _ in cards):
        return cards

    rarity = random.choices(
        GUARANTEE_RARITIES,
        weights=[RARITY_WEIGHTS[r] for r in GUARANTEE_RARITIES],
        k=1,
    )[0]
    cards[-1] = (random.choice(CARD_POOL[rarity]), rarity, True)
    return cards


def _format_ten(cards: list[tuple[str, str, bool]]) -> str:
    """把十连结果排成一条多行文本，保底那张带 ✨ 标记。"""
    lines = ["🎴 十连结果："]
    for i, (name, rarity, guaranteed) in enumerate(cards, start=1):
        mark = " ✨保底" if guaranteed else ""
        lines.append(f"{i}. 【{rarity}】{name}{mark}")
    return "\n".join(lines)


async def cmd_draw(bot, group_id, user_id, text):
    """处理 /抽卡：无参数单抽，带「十连」抽十张，其他参数给用法提示。"""
    cfg = load_feature_config("gacha")
    if not cfg.get("enabled", False):
        return None

    arg = text.strip()[len("/抽卡") :].strip()
    if not arg:
        name, rarity = draw_card()
        return f"🎴 抽卡结果：【{rarity}】{name}"
    if arg == "十连":
        return _format_ten(draw_ten())
    return USAGE


# ★ 必须导出 COMMANDS，机器人才能发现这个命令
COMMANDS = {
    "/抽卡": cmd_draw,
}

# COMMANDS 是精确匹配，接不住「/抽卡 十连」这种带参数的写法，
# 所以带参数的一律交给正则匹配，再在 cmd_draw 里按参数分流。
COMMAND_PATTERNS = {
    r"^/抽卡\s+.*$": cmd_draw,
}

PATTERN_HELP = {
    r"^/抽卡\s+.*$": "/抽卡 十连",
}
