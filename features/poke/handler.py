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


def _cfg_number(cfg: dict, key: str, default, cast=float, minimum=None, maximum=None):
    """安全读一个数字配置：类型不对或超出范围就回退默认值，并打一条 warning。

    配置写错时如果直接抛异常，表现是「戳了没反应」，日志里还看不出原因；
    这里统一兜住，让功能退化成默认值继续跑，同时在日志里留下线索。
    """
    raw = cfg.get(key, default)
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        logger.warning(
            f"configs/poke.yaml 的 {key} 不是合法 {cast.__name__}（{raw!r}），"
            f"回退默认值 {default}"
        )
        return default
    if minimum is not None and value < minimum:
        logger.warning(f"configs/poke.yaml 的 {key}={value} 小于 {minimum}，回退默认值 {default}")
        return default
    if maximum is not None and value > maximum:
        logger.warning(f"configs/poke.yaml 的 {key}={value} 大于 {maximum}，回退默认值 {default}")
        return default
    return value


def _prune_stale(now: float, window: float) -> None:
    """清掉窗口内已经没有有效记录的群，避免字典随加过的群无限增长。

    每次被戳时调用一次，量级是「有记录的群数」，开销可以忽略。
    """
    for key in list(_recent):
        if now < _cooldown_until.get(key, 0.0):
            continue  # 还在倒地，留着
        times = _recent[key]
        if not times or now - times[-1] > window:
            _recent.pop(key, None)
            _cooldown_until.pop(key, None)


def _render_spam_reply(cfg: dict, cooldown: float) -> str | None:
    """渲染戳死台词：{seconds} 换成实际冷却秒数，模板写错就按原样发送。"""
    template = cfg.get("spam_reply")
    if not template:
        return None
    try:
        return str(template).format(seconds=int(cooldown))
    except (KeyError, IndexError, ValueError):
        logger.warning(f"configs/poke.yaml 的 spam_reply 占位符无法识别，按原样发送：{template!r}")
        return str(template)


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

    # 配置全部走安全转换：写错就回退默认值 + 打 warning，不让功能静默失效
    window = _cfg_number(cfg, "spam_window_seconds", 60.0, float, minimum=0.0)
    threshold = _cfg_number(cfg, "spam_threshold", 15, int, minimum=1)
    cooldown = _cfg_number(cfg, "spam_cooldown_seconds", 30.0, float, minimum=0.0)
    chance = _cfg_number(cfg, "poke_back_chance", 0.3, float, minimum=0.0, maximum=1.0)

    key = str(group_id)
    now = time.monotonic()

    # 顺手清掉早已过期、不会再被用到的群
    _prune_stale(now, window)

    # ① 倒地中（被戳死还没复活）：彻底静默，防止刷屏
    if now < _cooldown_until.get(key, 0.0):
        return None

    # ② 记下这一次，并数出窗口内的总次数
    times = _recent.setdefault(key, [])
    times.append(now)
    while times and now - times[0] > window:
        times.pop(0)
    count = len(times)

    # ③ 戳死：全群被戳满阈值 → 回一句"被戳死了"，然后整群静默 cooldown 秒
    if count >= threshold:
        _cooldown_until[key] = now + cooldown
        _recent[key] = []
        logger.info(
            f"[群:{group_id}] {window:.0f} 秒内被戳 {count} 次（最后一次来自 {user_id}），"
            f"戳死，倒地 {cooldown:.0f} 秒"
        )
        return _render_spam_reply(cfg, cooldown)

    # ④ 正常：掷一次骰子决定这次的反应——要么反戳，要么回话（replies 为空时才可能都不做）
    if random.random() < chance:
        await bot.group_poke(group_id, user_id)
        logger.info(f"[群:{group_id}] 反戳 {user_id}")
        return None

    replies = cfg.get("replies") or []
    if replies:
        return random.choice(replies)

    return None


# ★ 导出 POKE_HANDLERS，discover() 会自动收走
POKE_HANDLERS = [handle_poke]
