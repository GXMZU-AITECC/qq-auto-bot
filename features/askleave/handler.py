"""请假登记与班次提醒。

两件事：
1. 群里发「请假 一班次 去医院」当场登记并回复确认，也支持取消、查名单。
2. 后台 long-running 任务在每个班次到岗前 notify_before_minutes 分钟，
   把该班次的请假名单发到群里（没人请假就不打扰）。

班次定义直接读签到功能的 configs/checkin.yaml::checkin_shifts，
两边共用一份，改时间点只改一处，不会出现「签到认这个班次、请假认另一个」的情况。
"""

import asyncio
import logging
import re
from datetime import date, datetime, timedelta

from config import load_feature_config

from . import storage

logger = logging.getLogger("features.askleave")

CFG_NAME = "askleave"
TIMEZONE = timedelta(hours=8)
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
DAY_WORDS = {"今天": 0, "明天": 1, "后天": 2}
_DIGIT2CN = {"1": "一", "2": "二", "3": "三", "4": "四"}

# 「今天 / 明天 / 10-20 / 2026-10-20」都认
_DAY_PAT = r"(?:今天|明天|后天|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2})"


def _now() -> datetime:
    return datetime.utcnow() + TIMEZONE


def _today() -> date:
    return _now().date()


# ---------------------------------------------------------------- 班次

def _parse_hhmm(value) -> int | None:
    """把 "07:40" 转成当天分钟数，格式不对返回 None。"""
    try:
        hour, minute = str(value).split(":")[:2]
        return int(hour) * 60 + int(minute)
    except (ValueError, AttributeError):
        return None


def shifts(cfg: dict | None = None) -> list[dict]:
    """班次列表，来自签到配置。[{name, arrive, arrive_m}]"""
    cfg = cfg if cfg is not None else load_feature_config("checkin")
    out = []
    for item in cfg.get("checkin_shifts") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        arrive_m = _parse_hhmm(item.get("arrive"))
        if arrive_m is None:
            continue
        out.append({
            "name": str(item["name"]),
            "arrive": str(item.get("arrive") or ""),
            "arrive_m": arrive_m,
        })
    return out


def _norm_period(token: str, names: list[str]) -> str | None:
    """把群友写的班次写法归一到配置里的班次名，认不出来返回 None。"""
    token = (token or "").strip()
    if not token:
        return None
    if token in names:
        return token
    if token.startswith("晚"):  # 晚班 / 晚自修 都认晚班
        for name in names:
            if name.startswith("晚"):
                return name
    m = re.fullmatch(r"([1-4])班(次)?", token)  # 1班次 / 2班 → 二班次
    if m:
        for name in names:
            if name.startswith(_DIGIT2CN[m.group(1)]):
                return name
    return None


def _arrive_of(period: str, cfg: dict | None = None) -> str:
    for shift in shifts(cfg):
        if shift["name"] == period:
            return shift["arrive"]
    return ""


# ---------------------------------------------------------------- 解析

def _parse_day(word) -> date | None:
    """把日期词转成 date；认不出来返回 None，由调用方给提示。"""
    if word is None:
        return None
    raw = str(word).strip().replace("/", "-")
    if raw in DAY_WORDS:
        return _today() + timedelta(days=DAY_WORDS[raw])
    try:
        parts = [int(p) for p in raw.split("-")]
    except ValueError:
        return None
    if len(parts) == 2:
        month, day = parts
        today = _today()
        # 填的月份远小于当前月份，按跨年理解（12 月填 01-05 指的是明年）
        year = today.year + 1 if month < today.month - 6 else today.year
        try:
            return date(year, month, day)
        except ValueError:
            return None
    if len(parts) >= 3:
        try:
            return date(parts[0], parts[1], parts[2])
        except ValueError:
            return None
    return None


def _take_day(body: str):
    """从消息开头剥掉日期词，返回 (day|None, 剩余文本)。"""
    m = re.match(rf"^({_DAY_PAT})\s*", body)
    if not m:
        return None, body
    return _parse_day(m.group(1)), body[m.end():]


def _take_periods(body: str, names: list[str]):
    """从头连续吃掉班次名（可多个），返回 ([班次名], 剩余文本)。

    按空白切词，逐词归一化；一旦认不出就停下，剩下的整段当作请假原因。
    """
    periods: list[str] = []
    while True:
        m = re.match(r"^(\S+)\s*", body)  # 贪婪取词，不能非贪婪，否则会切出单字
        if not m:
            break
        hit = _norm_period(m.group(1), names)
        if hit is None:
            break
        if hit not in periods:
            periods.append(hit)
        body = body[m.end():]
    return periods, body


def parse_leave(text: str, cfg: dict | None = None):
    """解析请假消息：「请假 [今天] 一班次 [二班次] [原因]」。

    返回 (day, periods, reason, err)，err 非空表示解析失败，文案可直接回复群里。
    """
    names = [shift["name"] for shift in shifts(cfg)]
    if not names:
        return None, [], "", "班次还没配好，请联系管理员检查 configs/checkin.yaml 的 checkin_shifts。"

    body = re.sub(r"^\s*请假\s*", "", (text or "").strip())
    # 群里习惯用顿号/逗号连写多个班次，先摊成空格再逐词解析
    body = re.sub(r"[、,，;；]+", " ", body)
    day, body = _take_day(body)
    periods, body = _take_periods(body, names)

    if not periods:
        return (day or _today()), [], "", (
            f"没认出班次，可用的是：{'、'.join(names)}\n例：「请假 明天 一班次」"
        )

    return (day or _today()), periods, body.strip(), ""


def _fmt_day(day: date) -> str:
    return f"{day.isoformat()}（{WEEKDAY_NAMES[day.weekday()]}）"


# ---------------------------------------------------------------- 命令

async def ask_leave(bot, group_id: str, user_id: str, text: str) -> str:
    """请假登记，当场回复确认。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", True):
        return None

    shift_cfg = load_feature_config("checkin")
    day, periods, reason, err = parse_leave(text, shift_cfg)
    if err:
        return err

    name = await bot.get_group_member_name(group_id, user_id)
    day_str = day.isoformat()

    added, dup = [], []
    for period in periods:
        ok = await asyncio.to_thread(
            storage.add, group_id, user_id, name, day_str, period, reason
        )
        (added if ok else dup).append(period)

    if not added:
        return f"你在 {_fmt_day(day)} 的「{'、'.join(dup)}」已经登记过请假了。"

    lines = [f"✅ {name} 请假已登记", f"📅 {_fmt_day(day)}"]
    for period in added:
        arrive = _arrive_of(period, shift_cfg)
        lines.append(f"🕐 {period}" + (f"（{arrive} 到岗）" if arrive else ""))
    if reason:
        lines.append(f"📝 原因：{reason}")
    if dup:
        lines.append(f"注：「{'、'.join(dup)}」之前已经登记过了")
    return "\n".join(lines)


async def cancel_leave(bot, group_id: str, user_id: str, text: str) -> str:
    """取消请假。不带班次则取消当天全部。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", True):
        return None

    body = re.sub(r"^\s*取消请假\s*", "", (text or "").strip())
    day, body = _take_day(body)
    day = day or _today()
    day_str = day.isoformat()

    names = [shift["name"] for shift in shifts()]
    periods, _ = _take_periods(body, names)

    mine = await asyncio.to_thread(storage.list_user_by_date, group_id, user_id, day_str)
    targets = [r for r in mine if r["period"] in periods] if periods else mine
    if not targets:
        return f"没查到你在 {_fmt_day(day)} 的请假记录。"

    for row in targets:
        await asyncio.to_thread(
            storage.remove, group_id, user_id, day_str, row["period"]
        )
    return f"✅ 已取消 {_fmt_day(day)} 的请假：{'、'.join(r['period'] for r in targets)}"


async def leave_list(bot, group_id: str, user_id: str, text: str) -> str:
    """查看某天的请假名单，默认今天。"""
    cfg = load_feature_config(CFG_NAME)
    if not cfg.get("enabled", True):
        return None

    m = re.search(_DAY_PAT, re.sub(r"^\s*请假名单\s*", "", (text or "").strip()))
    day = _parse_day(m.group(0)) if m else _today()
    rows = await asyncio.to_thread(storage.list_by_date, group_id, day.isoformat())

    if not rows:
        return f"{_fmt_day(day)} 没有人请假。"

    lines = [f"📋 {_fmt_day(day)} 请假名单："]
    for row in rows:
        name = row["user_name"] or row["user_id"]
        line = f"  · {name} {row['period']}"
        if row["reason"]:
            line += f"（{row['reason']}）"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------- 后台提醒

def _sleep_to_next_minute() -> float:
    now = _now()
    return 60 - now.second - now.microsecond / 1_000_000 + 0.05


def notify_text(shift: dict, rows: list[dict], before: int) -> str:
    """班次开始前 minutes 分钟的提醒文案。"""
    names = []
    for row in rows:
        name = row["user_name"] or row["user_id"]
        names.append(f"{name}（{row['reason']}）" if row["reason"] else name)
    return (
        f"⏰ {shift['name']} {before} 分钟后开始（{shift['arrive']} 到岗）\n"
        f"今日请假：{'、'.join(names)}"
    )


def due_shifts(now: datetime, cfg: dict, today: str) -> list[dict]:
    """当前这一分钟该提醒哪些班次 —— 抽出来便于单测。"""
    try:
        before = int(cfg.get("notify_before_minutes") or 30)
    except (TypeError, ValueError):
        before = 30
    now_min = now.hour * 60 + now.minute
    return [s for s in shifts() if s["arrive_m"] - before == now_min]


async def run(bot):
    """STARTUP 目标：长驻提醒循环，每分钟对一次表。"""
    notified: set[tuple[str, str]] = set()
    last_minute: str | None = None

    while True:
        await asyncio.sleep(_sleep_to_next_minute())
        now = _now()
        key = now.strftime("%Y-%m-%d %H:%M")
        if key == last_minute:  # 重复唤醒去重
            continue
        last_minute = key

        today = now.strftime("%Y-%m-%d")
        notified = {(d, p) for d, p in notified if d == today}  # 只留当天

        for shift in due_shifts(now, load_feature_config(CFG_NAME), today):
            token = (today, shift["name"])
            if token in notified:
                continue
            notified.add(token)
            try:
                await tick_once(bot, now, shift)
            except Exception:
                logger.exception(f"请假提醒发送失败: {shift['name']}")


async def tick_once(bot, now: datetime, shift: dict) -> None:
    """单个班次的提醒动作，拆出来方便测试。"""
    today = now.strftime("%Y-%m-%d")
    before = int(load_feature_config(CFG_NAME).get("notify_before_minutes") or 30)
    groups = await asyncio.to_thread(storage.groups_with_leave, today, shift["name"])
    for group_id in groups:
        rows = await asyncio.to_thread(
            storage.list_by_period, group_id, today, shift["name"]
        )
        if not rows:
            continue
        await bot.send_group_msg(group_id, notify_text(shift, rows, before))


# ---------------------------------------------------------------- 导出

# 注：注册顺序即匹配顺序，名单/取消要排在「请假」前面，否则会被它吃掉
COMMAND_PATTERNS = {
    rf"^请假名单(?:\s+{_DAY_PAT})?\s*$": leave_list,
    rf"^取消请假(?:\s+{_DAY_PAT})?(?:\s+.{{0,30}})?\s*$": cancel_leave,
    r"^请假(?:\s*.{0,60})?$": ask_leave,
}

STARTUP = [run]
