import asyncio
import os
import re
import sqlite3

import pytest

from features.checkin import handler, storage

SHIFT_CFG = {
    "makeup_window_minutes": 15,
    "checkin_shifts": [
        {"name": "一班次", "arrive": "07:40", "leave": "09:20", "duration_hours": 2},
        {"name": "二班次", "arrive": "09:50", "leave": "12:20", "duration_hours": 3},
        {"name": "三班次", "arrive": "14:10", "leave": "15:50", "duration_hours": 2},
        {"name": "四班次", "arrive": "16:20", "leave": "18:00", "duration_hours": 2},
        {"name": "晚班", "arrive": "19:20", "leave": "22:00", "options_hours": [2, 3]},
    ],
}


class FakeBot:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    async def _api_call(self, action, params):
        self.calls.append((action, params))
        return self.result


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_FILE", str(tmp_path / "checkin.db"))
    monkeypatch.setattr(storage, "load_feature_config", lambda name: SHIFT_CFG)
    return tmp_path


def _bot(*members):
    return FakeBot({"status": "ok", "data": list(members)})


def _run(bot, text, group_id="100", user_id="200"):
    return asyncio.run(handler._makeup(bot, group_id, user_id, text))


def _rows():
    if not os.path.exists(storage.DB_FILE):
        return []
    conn = sqlite3.connect(storage.DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM records")]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _secs(t: str) -> int:
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def test_只发补签返回说明(env):
    reply = _run(_bot(), "补签")
    assert "补签 姓名 日期 班次" in reply
    assert "YYYY-MM-DD" in reply
    assert "晚班2" in reply and "晚班3" in reply
    assert "姓名#QQ" in reply


def test_日期格式错误(env):
    reply = _run(_bot(), "补签 小明 2026/10/18 三班次")
    assert "日期格式不对" in reply


def test_未来日期被拒绝(env):
    reply = _run(_bot({"user_id": 1, "card": "小明"}), "补签 小明 2999-12-31 三班次")
    assert "未来日期" in reply
    assert _rows() == []


def test_补签成功并落库(env):
    reply = _run(_bot({"user_id": 10001, "card": "小明", "nickname": "m"}),
                 "补签 小明 2020-01-15 三班次")
    assert "补签成功" in reply

    rows = _rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["group_id"] == "100"
    assert row["user_id"] == "10001"
    assert row["user_name"] == "小明"
    assert row["date"] == "2020-01-15"
    assert row["period"] == "三班次"
    assert row["duration"] == 2
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", row["time"])
    assert _secs("14:10:00") <= _secs(row["time"]) < _secs("14:25:00")


@pytest.mark.parametrize("shift,hours", [("晚班2", 2), ("晚班3", 3)])
def test_晚班带时长(env, shift, hours):
    reply = _run(_bot({"user_id": 1, "card": "小明"}), f"补签 小明 2020-01-15 {shift}")
    assert "补签成功" in reply
    row = _rows()[0]
    assert row["period"] == "晚班"
    assert row["duration"] == hours
    assert _secs("19:20:00") <= _secs(row["time"]) < _secs("19:35:00")


@pytest.mark.parametrize("shift,expected", [
    ("晚班", "请带上时长"),
    ("晚班4", "班次不存在"),
    ("五班次", "班次不存在"),
])
def test_班次写法错误(env, shift, expected):
    reply = _run(_bot({"user_id": 1, "card": "小明"}), f"补签 小明 2020-01-15 {shift}")
    assert expected in reply
    assert _rows() == []


def test_重复补签只写一条(env):
    bot = _bot({"user_id": 1, "card": "小明"})
    first = _run(bot, "补签 小明 2020-01-15 三班次")
    second = _run(bot, "补签 小明 2020-01-15 三班次")
    assert "补签成功" in first
    assert "已有签到记录" in second
    assert len(_rows()) == 1


def test_群名片优先于昵称(env):
    bot = _bot(
        {"user_id": 1, "card": "", "nickname": "小明"},
        {"user_id": 2, "card": "小明", "nickname": "other"},
    )
    _run(bot, "补签 小明 2020-01-15 三班次")
    assert _rows()[0]["user_id"] == "2"


def test_名片为空回落昵称(env):
    bot = _bot({"user_id": 3, "card": "", "nickname": "小明"})
    reply = _run(bot, "补签 小明 2020-01-15 三班次")
    assert "补签成功" in reply
    assert _rows()[0]["user_id"] == "3"
    assert _rows()[0]["user_name"] == "小明"


def test_找不到成员(env):
    reply = _run(_bot({"user_id": 1, "card": "小红"}), "补签 小明 2020-01-15 三班次")
    assert "没找到群成员" in reply
    assert _rows() == []


def test_同名多人返回候选列表(env):
    bot = _bot(
        {"user_id": 1, "card": "小明"},
        {"user_id": 2, "card": "小明"},
    )
    reply = _run(bot, "补签 小明 2020-01-15 三班次")
    assert "QQ 1" in reply and "QQ 2" in reply
    assert "小明#QQ" in reply
    assert _rows() == []


def test_重名时用QQ指定(env):
    bot = _bot(
        {"user_id": 1, "card": "小明"},
        {"user_id": 2, "card": "小明"},
    )
    reply = _run(bot, "补签 小明#2 2020-01-15 三班次")
    assert "补签成功" in reply
    assert _rows()[0]["user_id"] == "2"


def test_指定的QQ不存在(env):
    reply = _run(_bot({"user_id": 1, "card": "小明"}), "补签 小明#999 2020-01-15 三班次")
    assert "没找到 QQ 为 999" in reply
    assert _rows() == []


@pytest.mark.parametrize("result", [None, {"status": "failed"}, {"data": "oops"}])
def test_获取成员列表失败(env, result):
    reply = _run(FakeBot(result), "补签 小明 2020-01-15 三班次")
    assert "获取群成员列表失败" in reply


def test_随机窗口可配置且不超过班次结束(env, monkeypatch):
    shift = next(s for s in storage.shifts() if s["name"] == "一班次")
    cfg = dict(SHIFT_CFG, makeup_window_minutes=999)
    monkeypatch.setattr(storage, "load_feature_config", lambda name: cfg)
    monkeypatch.setattr(storage.random, "randrange", lambda n: n - 1)
    assert storage._makeup_time(shift) == "09:19:59"


def test_窗口配置非法回落默认(env, monkeypatch):
    shift = next(s for s in storage.shifts() if s["name"] == "一班次")
    cfg = dict(SHIFT_CFG, makeup_window_minutes="abc")
    monkeypatch.setattr(storage, "load_feature_config", lambda name: cfg)
    monkeypatch.setattr(storage.random, "randrange", lambda n: 0)
    assert storage._makeup_time(shift) == "07:40:00"


def test_parse_shift(env):
    assert storage.parse_shift("三班次")[1] == 2
    assert storage.parse_shift("晚班2")[1] == 2
    assert storage.parse_shift("晚班3")[1] == 3
    with pytest.raises(ValueError):
        storage.parse_shift("晚班")
    with pytest.raises(ValueError):
        storage.parse_shift("晚班4")
    with pytest.raises(ValueError):
        storage.parse_shift("五班次")
