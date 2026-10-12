"""定时消息：后台循环按 cron 到点触发，是否发送由工作日日历决定。"""

import asyncio
import logging
from datetime import datetime, timedelta

from config import load_feature_config

from . import calendar, cron

logger = logging.getLogger("features.scheduled")

TIMEZONE = timedelta(hours=8)

_last_minute: str | None = None
_last_refresh_day: str | None = None
_bg: set[asyncio.Task] = set()


def _now() -> datetime:
    return datetime.utcnow() + TIMEZONE


def load_entries() -> list[dict]:
    """读取并过滤 configs/scheduled.yaml 的有效条目（每轮热加载）。"""
    cfg = load_feature_config("scheduled")
    entries: list[dict] = []
    seen: set[str] = set()
    for item in cfg.get("scheduled_messages") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name or name in seen:
            continue
        if item.get("target") in (None, "") or not item.get("cron") or not item.get("message"):
            continue
        if not cron.is_valid(str(item["cron"])):
            continue
        seen.add(name)
        entries.append(item)
    return entries


def should_fire(entry: dict, now: datetime, workday_ok: bool | None) -> bool:
    """workday 模式下：时间按 cron，当天由日历决定；日历未知则回退完整 cron。"""
    expr = entry["cron"]
    if entry.get("workday") and workday_ok is not None:
        return bool(workday_ok) and cron.matches_time(expr, now)
    return cron.matches(expr, now)


async def _send(bot, entry: dict) -> None:
    target = str(entry["target"])
    msg = entry["message"]
    if entry.get("type") == "private":
        await bot.send_private_msg(target, msg)
    else:
        await bot.send_group_msg(target, msg)


async def _refresh(now: datetime) -> None:
    await calendar.ensure(now.year)
    if now.month >= 11:  # 年末提前备次年
        await calendar.ensure(now.year + 1)


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg.add(task)
    task.add_done_callback(_bg.discard)


async def _tick(bot, now: datetime) -> None:
    global _last_minute, _last_refresh_day
    minute_key = now.strftime("%Y-%m-%d %H:%M")
    if minute_key == _last_minute:  # 早醒/重复唤醒去重
        return
    _last_minute = minute_key

    day = now.strftime("%Y-%m-%d")
    if day != _last_refresh_day:
        _last_refresh_day = day
        _spawn(_refresh(now))  # 后台刷新，不阻塞本次发送

    workday_ok = calendar.is_workday(now.date())
    for entry in load_entries():
        if not entry.get("enable", True):
            continue
        if not should_fire(entry, now, workday_ok):
            continue
        name = entry["name"]
        try:
            await _send(bot, entry)
        except Exception:
            logger.exception(f"定时消息发送失败: {name}")


def _sleep_to_next_minute() -> float:
    now = _now()
    return 60 - now.second - now.microsecond / 1_000_000 + 0.05


async def run(bot) -> None:
    """STARTUP 目标：长驻定时循环。"""
    global _last_refresh_day
    now = _now()
    _last_refresh_day = now.strftime("%Y-%m-%d")
    await _refresh(now)  # 启动时先备好当年数据

    while True:
        await asyncio.sleep(_sleep_to_next_minute())
        try:
            await _tick(bot, _now())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("定时消息循环异常")
