"""早安功能：模糊触发、开关、缺配置、命令注册与 /help 展示。"""

import asyncio
import re

import features
import features.morning.handler as morning
from features.morning.handler import cmd_morning


def _patch(monkeypatch, enabled=True):
    cfg = {"enabled": enabled}
    monkeypatch.setattr(morning, "load_feature_config", lambda name: cfg)
    return cfg


def _say(text):
    return asyncio.run(cmd_morning(None, "111", "222", text))


def test_导出了正则与说明():
    assert list(morning.COMMAND_PATTERNS.values()) == [cmd_morning]
    # 每个正则都要有 PATTERN_HELP，否则 /help 会显示裸正则
    assert set(morning.COMMAND_PATTERNS) == set(morning.PATTERN_HELP)


def test_未启用时静默(monkeypatch):
    _patch(monkeypatch, enabled=False)
    assert _say("早安") is None


def test_缺配置时静默(monkeypatch):
    monkeypatch.setattr(morning, "load_feature_config", lambda name: {})
    assert _say("早安") is None


def test_整句早安回问候(monkeypatch):
    _patch(monkeypatch)
    assert _say("早安") == morning.GREETING


def test_框架路由能吃下早安开头的消息(monkeypatch):
    """dispatch 用 fullmatch，如果正则写成 ^早安 这里会挂 —— 正是要防的回归。"""
    _patch(monkeypatch)
    monkeypatch.setattr(features, "_commands", {})
    monkeypatch.setattr(
        features,
        "_patterns",
        [(re.compile(pat), fn) for pat, fn in morning.COMMAND_PATTERNS.items()],
    )

    for text in ("早安", "早安各位", "早安呀～今天也要加油"):
        assert asyncio.run(features.dispatch(None, "1", "2", text)) == morning.GREETING

    for text in ("你好", "大家早安"):
        assert asyncio.run(features.dispatch(None, "1", "2", text)) is None


def test_help_显示友好写法而非裸正则(monkeypatch):
    monkeypatch.setattr(features, "_commands", {})
    monkeypatch.setattr(
        features,
        "_patterns",
        [(re.compile(pat), fn) for pat, fn in morning.COMMAND_PATTERNS.items()],
    )
    monkeypatch.setattr(features, "_pattern_help", dict(morning.PATTERN_HELP))

    out = asyncio.run(features.dispatch(None, "1", "2", features.HELP_CMD))
    assert "早安（发「早安…」即触发）" in out
    assert r"^早安.*$" not in out
