"""Tests for the morning greeting feature."""

import asyncio
import re

from features.greeting.handler import COMMAND_PATTERNS, cmd_morning


def test_morning_greeting_exact():
    result = asyncio.run(cmd_morning(None, "1", "1", "早安"))
    assert result == "早安！今天也要开心哦～"


def test_morning_greeting_with_suffix():
    result = asyncio.run(cmd_morning(None, "1", "1", "早安呀"))
    assert result == "早安！今天也要开心哦～"


def test_pattern_matches_acceptance_criteria():
    pattern = list(COMMAND_PATTERNS.keys())[0]
    compiled = re.compile(pattern)
    assert compiled.fullmatch("早安")
    assert compiled.fullmatch("早安呀")
    assert not compiled.fullmatch("你好")
    assert not compiled.fullmatch("你好早安")
