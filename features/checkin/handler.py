import asyncio
import re
from datetime import datetime, timedelta, timezone

from . import storage

TIMEZONE = timedelta(hours=8)
_MAKEUP_PAT = re.compile(r"补签\s+(?P<name>.+?)\s+(?P<date>\S+)\s+(?P<shift>\S+)\s*")


def _extract_hours(text: str) -> int | None:
    m = re.search(r"\+(\d+)\s*$", text)
    return int(m.group(1)) if m else None


async def _checkin(bot, group_id: str, user_id: str, text: str) -> str:
    user_name = await bot.get_group_member_name(group_id, user_id)
    return await asyncio.to_thread(storage.checkin, group_id, user_id, user_name, _extract_hours(text))


def _today():
    return (datetime.now(timezone.utc) + TIMEZONE).date()


def _usage() -> str:
    tokens = []
    for shift in storage.shifts():
        if shift["options"]:
            tokens.extend(f"{shift['name']}{n}" for n in shift["options"])
        else:
            tokens.append(shift["name"])
    shift_text = " / ".join(tokens) or "一班次 / 二班次 / 三班次 / 四班次 / 晚班2 / 晚班3"
    return (
        "补签 姓名 日期 班次\n"
        "日期格式：YYYY-MM-DD（如 2026-10-18）\n"
        f"班次格式：{shift_text}\n"
        "重名时：补签 姓名#QQ 日期 班次"
    )


def _member_name(member: dict) -> str:
    return str(member.get("card") or "").strip() or str(member.get("nickname") or "").strip()


def _ambiguity(matches: list, name: str, field: str) -> str:
    lines = [f"「{name}」匹配到 {len(matches)} 个人（{field}相同）："]
    for i, m in enumerate(matches[:10], 1):
        lines.append(f"{i}. {_member_name(m)}（QQ {m.get('user_id')}）")
    if len(matches) > 10:
        lines.append(f"……还有 {len(matches) - 10} 人")
    lines.append(f"请改用：补签 {name}#QQ 日期 班次")
    return "\n".join(lines)


def _pick_member(members: list, name: str, qq: str | None = None):
    """返回 (member, None) 或 (None, 错误提示)。"""
    if qq:
        for m in members:
            if str(m.get("user_id")) == qq:
                return m, None
        return None, f"没找到 QQ 为 {qq} 的群成员。"

    cards = [m for m in members if str(m.get("card") or "").strip() == name]
    if len(cards) == 1:
        return cards[0], None
    if len(cards) > 1:
        return None, _ambiguity(cards, name, "群名片")

    nicks = [m for m in members if str(m.get("nickname") or "").strip() == name]
    if len(nicks) == 1:
        return nicks[0], None
    if len(nicks) > 1:
        return None, _ambiguity(nicks, name, "昵称")
    return None, f"没找到群成员「{name}」，请确认群名片是否正确。"


async def _find_member(bot, group_id: str, name: str, qq: str | None = None):
    result = await bot._api_call("get_group_member_list", {"group_id": int(group_id)})
    members = result.get("data") if isinstance(result, dict) else None
    if not isinstance(members, list):
        return None, "获取群成员列表失败，请稍后再试。"
    members = [m for m in members if isinstance(m, dict) and m.get("user_id") is not None]
    return _pick_member(members, name, qq)


async def _makeup(bot, group_id: str, user_id: str, text: str) -> str:
    m = _MAKEUP_PAT.fullmatch(text)
    if not m:
        return _usage()

    try:
        day = datetime.strptime(m.group("date"), "%Y-%m-%d").date()
    except ValueError:
        return "日期格式不对，应为 YYYY-MM-DD，如 2026-10-18。"
    if day > _today():
        return "不能补签未来日期。"

    raw_name = m.group("name").strip().replace("＃", "#")
    name, qq = raw_name, None
    if "#" in raw_name:
        base, tail = raw_name.rsplit("#", 1)
        if tail.isdigit():
            name, qq = base.strip(), tail

    member, error = await _find_member(bot, group_id, name, qq)
    if error:
        return error

    try:
        return await asyncio.to_thread(
            storage.makeup,
            group_id,
            str(member["user_id"]),
            _member_name(member),
            day.strftime("%Y-%m-%d"),
            m.group("shift"),
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
