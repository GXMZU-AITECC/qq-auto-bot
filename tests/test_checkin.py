import asyncio
import os
import re
import sqlite3
from datetime import timedelta

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
    def __init__(self, name="小明"):
        self.name = name

    async def get_group_member_name(self, group_id, user_id):
        return self.name


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_FILE", str(tmp_path / "checkin.db"))
    monkeypatch.setattr(storage, "load_feature_config", lambda name: SHIFT_CFG)
    return tmp_path


def _run(text, name="小明", user_id="200"):
    return asyncio.run(handler._makeup(FakeBot(name), "100", user_id, text))


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
    reply = _run("补签")
    assert "补签 日期 班次" in reply
    assert "只能补自己的" in reply
    assert "YYYY-MM-DD" in reply and "今天" in reply and "昨天" in reply
    assert "晚班2" in reply and "晚班3" in reply


def test_带姓名等多余参数返回说明(env):
    reply = _run("补签 小明 2020-01-15 三班次")
    assert "补签 日期 班次" in reply
    assert _rows() == []


def test_日期格式错误(env):
    reply = _run("补签 2026/10/18 三班次")
    assert "没认出日期" in reply
    assert _rows() == []


def test_只写日期提示带班次(env):
    assert "请带上班次" in _run("补签 今天")
    assert "请带上班次" in _run("补签 2020-01-15")
    assert _rows() == []


def test_未来日期被拒绝(env):
    reply = _run("补签 2999-12-31 三班次")
    assert "未来日期" in reply
    assert _rows() == []


def test_补签成功并落库(env):
    reply = _run("补签 2020-01-15 三班次", name="小明", user_id="10001")
    assert "补签成功" in reply
    assert "操作人：小明" in reply

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


def test_不写日期默认今天(env):
    _run("补签 三班次")
    assert _rows()[0]["date"] == handler._today().isoformat()


@pytest.mark.parametrize("token,delta", [("今天", 0), ("昨天", -1)])
def test_相对日期(env, token, delta):
    _run(f"补签 {token} 三班次")
    expect = (handler._today() + timedelta(days=delta)).isoformat()
    assert _rows()[0]["date"] == expect


@pytest.mark.parametrize("shift,hours", [("晚班2", 2), ("晚班3", 3)])
def test_晚班带时长(env, shift, hours):
    reply = _run(f"补签 2020-01-15 {shift}")
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
    reply = _run(f"补签 2020-01-15 {shift}")
    assert expected in reply
    assert _rows() == []


def test_重复补签不覆盖且带上原时间(env):
    first = _run("补签 2020-01-15 三班次")
    assert "补签成功" in first
    original = _rows()[0]
    second = _run("补签 2020-01-15 三班次")
    assert "已有签到记录" in second
    assert original["time"] in second
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["time"] == original["time"]


def test_只能给自己补签(env):
    _run("补签 2020-01-15 三班次", name="小明", user_id="1")
    _run("补签 2020-01-15 三班次", name="小红", user_id="2")
    rows = _rows()
    assert {(r["user_id"], r["user_name"]) for r in rows} == {("1", "小明"), ("2", "小红")}


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
