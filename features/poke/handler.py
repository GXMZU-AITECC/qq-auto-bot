"""戳一戳功能：机器人被戳时，按概率反戳或回一句话。

本功能走的是 **notice 事件**（不是聊天消息），所以不导出 COMMANDS，
而是导出 POKE_HANDLERS —— 由 features/__init__.py 的 dispatch_poke 路由过来。

计数与冷却都按「群」维度：一分钟内整个群被戳满阈值就触发，代价全群共担。

配置见 configs/poke.yaml。
"""

import logging
import random
import time

from config import load_feature_config

logger = logging.getLogger("features.poke")

# 群号 -> 最近被戳的时间戳；用来判断"疯狂戳"（按群统计，不区分是谁戳的）
_recent: dict[str, list[float]] = {}
# 群号 -> 冷却到期时刻（time.monotonic 的刻度）
_cooldown_until: dict[str, float] = {}


async def handle_poke(bot, group_id, user_id, target_id):
    """被戳时执行：戳死判定 → 反戳 → 回话。

    bot       → 机器人对象，调 API 用它
    group_id  → 群号
    user_id   → 戳的人
    target_id → 被戳的人（框架已过滤，这里恒等于机器人自己，用不上）
    """
    cfg = load_feature_config("poke")
    if not cfg.get("enabled", False):
        return None
    if not group_id or not user_id:
        return None

    key = str(group_id)
    now = time.monotonic()

    # ① 倒地中（被戳死还没复活）：彻底静默，防止刷屏
    if now < _cooldown_until.get(key, 0.0):
        return None

    # ② 记下这一次，并数出窗口内的总次数
    times = _recent.setdefault(key, [])
    times.append(now)
    window = float(cfg.get("spam_window_seconds", 60))
    while times and now - times[0] > window:
        times.pop(0)
    count = len(times)

    # ③ 戳死：全群被戳满阈值 → 回一句"被戳死了"，然后整群静默 cooldown_seconds 秒
    if count >= int(cfg.get("spam_threshold", 15)):
        _cooldown_until[key] = now + float(cfg.get("spam_cooldown_seconds", 30))
        _recent[key] = []
        logger.info(
            f"[群:{group_id}] {window:.0f} 秒内被戳 {count} 次"
            f"（最后一次来自 {user_id}），戳死，倒地中"
        )
        return cfg.get("spam_reply") or None

    # ④ 正常：掷一次骰子决定这次的反应——要么反戳，要么回话（replies 为空时才可能都不做）
    if random.random() < float(cfg.get("poke_back_chance", 0.3)):
        await bot.group_poke(group_id, user_id)
        logger.info(f"[群:{group_id}] 反戳 {user_id}")
        return None

    replies = cfg.get("replies") or []
    if replies:
        return random.choice(replies)

    return None


# ★ 导出 POKE_HANDLERS，discover() 会自动收走
POKE_HANDLERS = [handle_poke]
