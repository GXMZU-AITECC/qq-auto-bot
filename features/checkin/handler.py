import asyncio
import re
from datetime import date, datetime, timedelta, timezone

from . import storage

TIMEZONE = timedelta(hours=8)
_DATE_PAT = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")


def _extract_hours(text: str) -> int | None:
    m = re.search(r"\+(\d+)\s*$", text)
    return int(m.group(1)) if m else None


async def _checkin(bot, group_id: str, user_id: str, text: str) -> str:
    user_name = await bot.get_group_member_name(group_id, user_id)
    return await asyncio.to_thread(storage.checkin, group_id, user_id, user_name, _extract_hours(text))


def _today() -> date:
    return (datetime.now(timezone.utc) + TIMEZONE).date()


def _parse_date(token: str) -> date:
    if token == "今天":
        return _today()
    if token == "昨天":
        return _today() - timedelta(days=1)
    return datetime.strptime(token, "%Y-%m-%d").date()


def _usage() -> str:
    tokens = []
    for shift in storage.shifts():
        if shift["options"]:
            tokens.extend(f"{shift['name']}{n}" for n in shift["options"])
        else:
            tokens.append(shift["name"])
    shift_text = " / ".join(tokens) or "一班次 / 二班次 / 三班次 / 四班次 / 晚班2 / 晚班3"
    return (
        "补签 日期 班次（只能补自己的）\n"
        "日期：YYYY-MM-DD（如 2026-10-18）/ 今天 / 昨天，不写默认今天\n"
        f"班次：{shift_text}\n"
        "示例：补签 2026-10-18 三班次"
    )


async def _makeup(bot, group_id: str, user_id: str, text: str) -> str:
    m = re.fullmatch(r"补签\s+(.+)", text.strip())
    if not m:
        return _usage()

    tokens = m.group(1).split()
    if len(tokens) > 2:
        return _usage()
    if len(tokens) == 2:
        day_token, shift = tokens
        try:
            day = _parse_date(day_token)
        except ValueError:
            return (
                f"没认出日期「{day_token}」，写法：YYYY-MM-DD（如 2026-10-18）"
                "、今天、昨天，不写则默认今天。"
            )
    else:
        shift = tokens[0]
        if _DATE_PAT.fullmatch(shift) or shift in ("今天", "昨天"):
            return "请带上班次，如「补签 今天 三班次」。"
        day = _today()

    if day > _today():
        return "不能补签未来日期。"

    user_name = await bot.get_group_member_name(group_id, user_id)
    try:
        return await asyncio.to_thread(
            storage.makeup, group_id, str(user_id), user_name, day.isoformat(), shift
        )
    except ValueError as e:
        return str(e)


# 签到触发词："文综楼已到"、"博达楼已到" 等 "XX楼已到"；晚班可带 +N 后缀指定时长
COMMANDS = {
    "补签": _makeup,
}

COMMAND_PATTERNS = {
    r"^[\u4e00-\u9fa5]+楼已到(?:\+\d{1,2})?$": _checkin,
    r"^补签\s+.+$": _makeup,
}
