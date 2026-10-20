"""/时间：验证中文格式、北京时间、命令注册和配置开关。"""

import asyncio
import re
from datetime import datetime, timedelta, timezone

import pytest

import features
from features.time import handler


def freeze_time(monkeypatch, instant):
    """只替换时间功能的时钟，不改系统时间。"""
    class FrozenDatetime:
        @staticmethod
        def now(tz):
            assert tz.utcoffset(None) == timedelta(hours=8)
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


def test_精确命令注册和help展示(monkeypatch):
    assert handler.COMMANDS == {"/时间": handler.cmd_time}
    monkeypatch.setattr(features, "_commands", handler.COMMANDS.copy())
    monkeypatch.setattr(features, "_patterns", [])
    monkeypatch.setattr(handler, "load_feature_config", lambda name: {"enabled": True})
    freeze_time(monkeypatch, datetime(2026, 10, 19, 8, 9, 5, tzinfo=handler.BEIJING))
    assert asyncio.run(features.dispatch(None, "1", "2", "/时间")).startswith("现在是 ")
    assert "/时间" in asyncio.run(features.dispatch(None, "1", "2", "/help"))
    assert asyncio.run(features.dispatch(None, "1", "2", "/时间 abc")) is None
