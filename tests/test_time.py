"""验证北京时间、多时区（含夏令时）、日期倒计时与命令路由。"""

import asyncio
import re
from datetime import datetime, timedelta, timezone

import pytest

import features
from features.time import handler


def freeze_time(monkeypatch, instant):
    """只替换时间功能的时钟，不改系统时间。"""
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz):
            assert tz is not None
            return instant.astimezone(tz)

    monkeypatch.setattr(handler, "datetime", FrozenDatetime)


def test_时间格式是中文且完整():
    text = handler.now_text()
    assert re.fullmatch(
        r"\d{4}年\d{1,2}月\d{1,2}日 星期[一二三四五六日] \d{2}:\d{2}:\d{2}", text
    ), text


@pytest.mark.parametrize("day, weekday", [(19 + i, w) for i, w in enumerate("一二三四五六日")])
def test_七天星期对应正确(monkeypatch, day, weekday):
    freeze_time(monkeypatch, datetime(2026, 10, day, 8, 9, 5, tzinfo=handler.BEIJING))
    assert handler.now_text() == f"2026年10月{day}日 星期{weekday} 08:09:05"


def test_UTC跨日转换为北京时间(monkeypatch):
    freeze_time(monkeypatch, datetime(2026, 10, 18, 16, 9, 5, tzinfo=timezone.utc))
    assert handler.now_text() == "2026年10月19日 星期一 00:09:05"


def test_每次调用获取新时间(monkeypatch):
    instant = datetime(2026, 10, 19, 8, 9, 5, tzinfo=handler.BEIJING)
    freeze_time(monkeypatch, instant)
    assert handler.now_text().endswith("08:09:05")
    freeze_time(monkeypatch, instant + timedelta(seconds=1))
    assert handler.now_text().endswith("08:09:06")


def test_启用时回复当前时间(monkeypatch):
    def load_config(name):
        assert name == "time"
        return {"enabled": True}

    monkeypatch.setattr(handler, "load_feature_config", load_config)
    freeze_time(monkeypatch, datetime(2026, 10, 19, 8, 9, 5, tzinfo=handler.BEIJING))
    reply = asyncio.run(handler.cmd_time(None, "1", "2", "/时间"))
    assert reply == "现在是 2026年10月19日 星期一 08:09:05（北京时间）"


@pytest.mark.parametrize("cfg", [{"enabled": False}, {}])
def test_关闭或缺配置时静默(monkeypatch, cfg):
    monkeypatch.setattr(handler, "load_feature_config", lambda name: cfg)
    assert asyncio.run(handler.cmd_time(None, "1", "2", "/时间")) is None


@pytest.fixture
def time_router(monkeypatch):
    """使用框架的真实路由，不改其他功能的注册状态。"""
    monkeypatch.setattr(features, "_commands", handler.COMMANDS.copy())
    monkeypatch.setattr(features, "_patterns", [
        (re.compile(pattern), command)
        for pattern, command in handler.COMMAND_PATTERNS.items()
    ])
    monkeypatch.setattr(handler, "load_feature_config", lambda name: {"enabled": True})
    freeze_time(monkeypatch, datetime(2026, 10, 19, 8, 9, 5, tzinfo=handler.BEIJING))

    def dispatch(text):
        return asyncio.run(features.dispatch(None, "1", "2", text))

    return dispatch


def test_精确命令注册和help展示(time_router):
    assert handler.COMMANDS == {
        "/时间": handler.cmd_time,
        "/倒计时": handler.cmd_countdown,
    }
    assert time_router("/时间") == "现在是 2026年10月19日 星期一 08:09:05（北京时间）"
    help_text = time_router("/help")
    assert "/时间" in help_text
    assert "/倒计时" in help_text
    assert "未知时区" in time_router("/时间 abc")


@pytest.mark.parametrize("query, expected", [
    ("UTC", "2026年10月19日 星期一 00:09:05（UTC时间）"),
    ("utc", "2026年10月19日 星期一 00:09:05（UTC时间）"),
    ("GMT", "2026年10月19日 星期一 00:09:05（UTC时间）"),
    ("东京", "2026年10月19日 星期一 09:09:05（东京时间）"),
    ("Tokyo", "2026年10月19日 星期一 09:09:05（东京时间）"),
    ("Asia/Tokyo", "2026年10月19日 星期一 09:09:05（东京时间）"),
    ("纽约", "2026年10月18日 星期日 20:09:05（纽约时间）"),
    ("New York", "2026年10月18日 星期日 20:09:05（纽约时间）"),
    ("America/New_York", "2026年10月18日 星期日 20:09:05（纽约时间）"),
    ("伦敦", "2026年10月19日 星期一 01:09:05（伦敦时间）"),
    ("London", "2026年10月19日 星期一 01:09:05（伦敦时间）"),
    ("Europe/London", "2026年10月19日 星期一 01:09:05（伦敦时间）"),
    ("北京", "2026年10月19日 星期一 08:09:05（北京时间）"),
    ("北京时间", "2026年10月19日 星期一 08:09:05（北京时间）"),
    ("Beijing", "2026年10月19日 星期一 08:09:05（北京时间）"),
    ("Asia/Shanghai", "2026年10月19日 星期一 08:09:05（北京时间）"),
])
def test_多时区和别名(time_router, query, expected):
    assert time_router(f"/时间 {query}") == f"现在是 {expected}"


@pytest.mark.parametrize("instant, query, expected", [
    (datetime(2026, 1, 1, 2, tzinfo=timezone.utc), "纽约", "2025年12月31日 星期三 21:00:00"),
    (datetime(2026, 7, 1, 2, tzinfo=timezone.utc), "纽约", "2026年6月30日 星期二 22:00:00"),
    (datetime(2026, 1, 1, 2, tzinfo=timezone.utc), "伦敦", "2026年1月1日 星期四 02:00:00"),
    (datetime(2026, 7, 1, 2, tzinfo=timezone.utc), "伦敦", "2026年7月1日 星期三 03:00:00"),
    (datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc), "纽约", "2026年3月8日 星期日 01:59:00"),
    (datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc), "纽约", "2026年3月8日 星期日 03:00:00"),
    (datetime(2026, 11, 1, 5, 59, tzinfo=timezone.utc), "纽约", "2026年11月1日 星期日 01:59:00"),
    (datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc), "纽约", "2026年11月1日 星期日 01:00:00"),
])
def test_夏令时及跨日跨年(time_router, monkeypatch, instant, query, expected):
    freeze_time(monkeypatch, instant)
    assert time_router(f"/时间 {query}") == f"现在是 {expected}（{query}时间）"


@pytest.mark.parametrize("text", ["/时间 abc", "/时间 火星", "/时间 东京 UTC"])
def test_非法时区列出可用列表(time_router, text):
    reply = time_router(text)
    assert "未知时区" in reply
    for name in handler.TIMEZONES:
        assert name in reply


@pytest.mark.parametrize("text", ["/时间 ", "/时间\t", "/时间\u3000"])
def test_只有空白参数保持原行为(time_router, text):
    assert time_router(text) == time_router("/时间")


@pytest.mark.parametrize("text", ["/时间  东京  ", "/时间\t东京", "/时间\u3000东京"])
def test_多时区参数允许空白(time_router, text):
    assert time_router(text) == time_router("/时间 东京")


def test_缺失时区数据给出提示(time_router, monkeypatch):
    def missing_zone(name):
        raise handler.ZoneInfoNotFoundError(name)

    monkeypatch.setattr(handler, "ZoneInfo", missing_zone)
    assert "tzdata" in time_router("/时间 纽约")
    assert "命令执行出错" not in time_router("/时间 纽约")
    assert time_router("/时间").endswith("（北京时间）")


@pytest.mark.parametrize("instant, target, expected", [
    (datetime(2026, 10, 19, 8, 9, 5, tzinfo=handler.BEIJING), "2026-12-31", "72 天 15 时 50 分"),
    (datetime(2026, 12, 31, 23, 30, tzinfo=handler.BEIJING), "2027-01-01", "0 天 0 时 30 分"),
    (datetime(2028, 2, 28, 12, tzinfo=handler.BEIJING), "2028-03-01", "1 天 12 时 0 分"),
    (datetime(2026, 10, 19, 15, 30, tzinfo=timezone.utc), "2026-10-20", "0 天 0 时 30 分"),
    (datetime(2026, 10, 19, 23, 59, 30, tzinfo=handler.BEIJING), "2026-10-20", "0 天 0 时 0 分（不足 1 分钟）"),
])
def test_倒计时按北京零点分解(time_router, monkeypatch, instant, target, expected):
    freeze_time(monkeypatch, instant)
    assert time_router(f"/倒计时 {target}") == (
        f"距离 {target} 00:00（北京时间）还剩 {expected}"
    )


@pytest.mark.parametrize("instant", [
    datetime(2026, 12, 31, 0, 0, tzinfo=handler.BEIJING),
    datetime(2026, 12, 31, 0, 0, 1, tzinfo=handler.BEIJING),
    datetime(2027, 1, 1, 0, 0, tzinfo=handler.BEIJING),
])
def test_目标到达或已过提示(time_router, monkeypatch, instant):
    freeze_time(monkeypatch, instant)
    assert "已到达或已过" in time_router("/倒计时 2026-12-31")


@pytest.mark.parametrize("text", ["/倒计时", "/倒计时 ", "/倒计时\t"])
def test_倒计时缺参数给用法(time_router, text):
    assert "用法：/倒计时 YYYY-MM-DD" in time_router(text)


@pytest.mark.parametrize("argument", [
    "2026-2-01", "2026-02-1", "20261231", "2026/12/31", "26-12-31",
    "2026-12-31T00:00", "2026-12-31 extra", "２０２６-１２-３１", "abc",
])
def test_倒计时严格日期格式(time_router, argument):
    assert "日期格式不正确" in time_router(f"/倒计时 {argument}")


@pytest.mark.parametrize("argument", [
    "2026-02-29", "2026-04-31", "2026-13-01", "2026-00-01", "2026-01-00", "0000-01-01",
])
def test_倒计时非法日历日期(time_router, argument):
    assert "日期无效" in time_router(f"/倒计时 {argument}")


def test_倒计时允许两端空白(time_router):
    assert time_router("/倒计时\t2026-12-31  ") == time_router("/倒计时 2026-12-31")


@pytest.mark.parametrize("cfg", [{"enabled": False}, {}])
@pytest.mark.parametrize("text", [
    "/时间", "/时间 东京", "/时间 火星", "/倒计时", "/倒计时 2026-12-31", "/倒计时 abc",
])
def test_关闭时所有命令均静默(time_router, monkeypatch, cfg, text):
    monkeypatch.setattr(handler, "load_feature_config", lambda name: cfg)
    assert time_router(text) is None


@pytest.mark.parametrize("text", [
    "/时间东京", "/时间表", "/倒计时器", "/倒计时2026-12-31", "普通消息", "/时间 东京\n额外内容",
])
def test_不误匹配其他消息(time_router, text):
    assert time_router(text) is None
