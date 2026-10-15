"""Tests for the morning greeting feature."""

import pytest

from features.greeting.handler import cmd_morning


@pytest.mark.asyncio
async def test_morning_greeting_exact():
    result = await cmd_morning(None, "1", "1", "早安")
    assert result == "早安！今天也要开心哦～"


@pytest.mark.asyncio
async def test_morning_greeting_with_suffix():
    result = await cmd_morning(None, "1", "1", "早安呀")
    assert result == "早安！今天也要开心哦～"


def test_pattern_does_not_match_other():
    import re
    from features.greeting.handler import COMMAND_PATTERNS
    pattern = list(COMMAND_PATTERNS.keys())[0]
    assert re.fullmatch(pattern, "早安")
    assert re.fullmatch(pattern, "早安呀")
    assert not re.fullmatch(pattern, "你好")
    assert not re.fullmatch(pattern, "你好早安")
