"""ping 功能：次数解析、开关、单次/连发输出，以及只走公开 API 入口。"""

import asyncio
import inspect

import features.ping.handler as ping


class FakeBot:
    """只实现 ping 用得到的公开方法，并记录被调用的次数。"""

    def __init__(self):
        self.calls = 0

    async def api_call(self, action, params=None):
        self.calls += 1
        return {"status": "ok", "data": {}}


def _patch(monkeypatch, enabled=True):
    cfg = {"enabled": enabled}
    monkeypatch.setattr(ping, "load_feature_config", lambda name: cfg)


def test_解析次数():
    assert ping.parse_times("/ping") == 1
    assert ping.parse_times("/ping 5") == 5
    assert ping.parse_times("/ping 10") == 10
    assert ping.parse_times("/ping  3 ") == 3


def test_非法次数返回_None():
    for bad in ("/ping 0", "/ping 11", "/ping abc", "/ping -1", "/ping 3.5", "/ping 一"):
        assert ping.parse_times(bad) is None, bad


def test_未启用时静默且不发请求(monkeypatch):
    _patch(monkeypatch, enabled=False)
    bot = FakeBot()
    assert asyncio.run(ping.cmd_ping(bot, "1", "2", "/ping")) is None
    assert bot.calls == 0


def test_单次不带序号(monkeypatch):
    _patch(monkeypatch)
    bot = FakeBot()
    out = asyncio.run(ping.cmd_ping(bot, "1", "2", "/ping"))
    assert out.startswith("pong 🏓 ")
    assert out.endswith("ms")
    assert "[" not in out
    assert bot.calls == 1


def test_连发按次数逐条列出(monkeypatch):
    _patch(monkeypatch)
    bot = FakeBot()
    lines = asyncio.run(ping.cmd_ping(bot, "1", "2", "/ping 3")).split("\n")
    assert len(lines) == 3
    assert lines[0].startswith("[1/3] pong")
    assert lines[2].startswith("[3/3] pong")
    assert bot.calls == 3


def test_非法参数回用法且不发请求(monkeypatch):
    _patch(monkeypatch)
    bot = FakeBot()
    assert asyncio.run(ping.cmd_ping(bot, "1", "2", "/ping 99")) == ping.USAGE
    assert bot.calls == 0


def test_功能层不再直接调私有_api_call():
    """功能代码只能碰 bot 的公开方法，避免重构 bot.py 时连带改功能。"""
    src = inspect.getsource(ping)
    assert "_api_call" not in src
    assert "api_call(API_ACTION" in src


def test_有_PATTERN_HELP_覆盖所有正则():
    assert set(ping.COMMAND_PATTERNS) == set(ping.PATTERN_HELP)
