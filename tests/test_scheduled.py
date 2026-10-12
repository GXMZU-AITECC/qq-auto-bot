import asyncio
from datetime import date, datetime

import features.scheduled.calendar as calendar
from features.scheduled import cron
from features.scheduled.scheduler import _send, should_fire


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


# 2026-06-15 周一；2026-06-20 周六
_MON = _dt("2026-06-15 09:00")
_SAT = _dt("2026-06-20 09:00")
_WD_ENTRY = {"name": "x", "cron": "0 9 * * 1-5", "workday": True}


# ---------- cron ----------
def test_matches_time():
    assert cron.matches_time("30 7 * * 1-5", _dt("2026-06-15 07:30"))
    assert not cron.matches_time("30 7 * * 1-5", _dt("2026-06-15 07:31"))
    assert not cron.matches_time("bad expr", _dt("2026-06-15 07:30"))


def test_matches_full():
    assert cron.matches("30 7 * * 1-5", _dt("2026-06-15 07:30"))
    assert not cron.matches("30 7 * * 1-5", _dt("2026-06-20 07:30"))


# ---------- should_fire ----------
def test_should_fire_calendar_known_wins():
    assert should_fire(_WD_ENTRY, _MON, True)      # 工作日
    assert should_fire(_WD_ENTRY, _SAT, True)      # 调休补班周末，忽略周字段
    assert not should_fire(_WD_ENTRY, _MON, False)  # 法定节假日，忽略周字段


def test_should_fire_calendar_unknown_falls_back_to_cron():
    assert should_fire(_WD_ENTRY, _MON, None)       # 周一，cron 1-5
    assert not should_fire(_WD_ENTRY, _SAT, None)   # 周六，cron 1-5 不含


def test_should_fire_plain_cron():
    entry = {"name": "x", "cron": "0 9 * * 1-5"}
    assert should_fire(entry, _MON, None)
    assert not should_fire(entry, _SAT, None)


def test_should_fire_time_mismatch():
    assert not should_fire(_WD_ENTRY, _dt("2026-06-15 09:01"), True)


# ---------- calendar 解析 ----------
def test_parse_days_timor():
    payload = {
        "code": 0,
        "holiday": {
            "10-10": {"holiday": False, "name": "补班", "date": "2026-10-10"},
            "10-01": {"holiday": True, "name": "国庆", "date": "2026-10-01"},
        },
    }
    assert calendar._parse_days(payload, 2026) == {"2026-10-10": False, "2026-10-01": True}


def test_parse_days_apihubs():
    payload = {"code": 0, "data": {"list": [
        {"date": 20261010, "workday": 1},
        {"date": 20261001, "workday": 2},
    ]}}
    assert calendar._parse_days(payload, 2026) == {"2026-10-10": False, "2026-10-01": True}


def test_parse_days_empty_or_wrong_year_is_none():
    assert calendar._parse_days({"holiday": {}}, 2027) is None
    assert calendar._parse_days({}, 2027) is None
    assert calendar._parse_days({"holiday": {"01-01": {"holiday": True, "date": "2025-01-01"}}}, 2026) is None


# ---------- is_workday ----------
def test_is_workday_from_table(monkeypatch):
    table = {"2026-10-10": False, "2026-10-01": True}
    monkeypatch.setattr(calendar, "_load_cache", lambda year: table if year == 2026 else None)
    calendar._mem.clear()
    assert calendar.is_workday(date(2026, 10, 10)) is True    # 调休补班周六
    assert calendar.is_workday(date(2026, 10, 1)) is False    # 节假日
    assert calendar.is_workday(date(2026, 6, 15)) is True     # 普通周一
    assert calendar.is_workday(date(2026, 6, 20)) is False    # 普通周六


def test_is_workday_unknown(monkeypatch):
    monkeypatch.setattr(calendar, "_load_cache", lambda year: None)
    calendar._mem.clear()
    assert calendar.is_workday(date(2027, 1, 1)) is None


# ---------- 发送分发 ----------
class _FakeBot:
    def __init__(self):
        self.calls = []

    async def send_group_msg(self, group_id, text):
        self.calls.append(("group", group_id, text))

    async def send_private_msg(self, user_id, text):
        self.calls.append(("private", user_id, text))


def test_send_dispatch():
    bot = _FakeBot()
    asyncio.run(_send(bot, {"type": "group", "target": 123, "message": "hi"}))
    asyncio.run(_send(bot, {"type": "private", "target": 456, "message": "yo"}))
    assert bot.calls == [("group", "123", "hi"), ("private", "456", "yo")]
