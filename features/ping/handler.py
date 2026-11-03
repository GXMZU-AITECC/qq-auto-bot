"""/ping：回复 pong，并显示一次 LLOneBot API 往返的耗时。

用法：
  /ping      测一次
  /ping 5    连测 5 次，逐条列出
"""

import time
from typing import Optional

from config import load_feature_config

MAX_TIMES = 10
USAGE = "用法：/ping [次数]，次数范围 1~10"

# 用一个轻量、无副作用的接口来测往返延迟
API_ACTION = "get_login_info"


def parse_times(text: str) -> Optional[int]:
    """解析 /ping 后面的次数；不带参数视为 1 次，非法返回 None"""
    arg = text[len("/ping"):].strip()
    if arg == "":
        return 1
    if arg.isdigit() and 1 <= int(arg) <= MAX_TIMES:
        return int(arg)
    return None


async def _measure(bot) -> int:
    """调一次 API，返回耗时（毫秒）"""
    start = time.perf_counter()
    await bot.api_call(API_ACTION, {})
    return int((time.perf_counter() - start) * 1000)


async def cmd_ping(bot, group_id, user_id, text):
    """处理 /ping [次数]：未启用时静默，参数非法时给用法。"""
    cfg = load_feature_config("ping")
    if not cfg or not cfg.get("enabled", False):
        return None

    times = parse_times(text)
    if times is None:
        return USAGE

    results = []
    for i in range(times):
        ms = await _measure(bot)
        if times == 1:
            results.append(f"pong 🏓 {ms}ms")
        else:
            results.append(f"[{i + 1}/{times}] pong 🏓 {ms}ms")

    return "\n".join(results)


# ★ 带参数的命令必须用正则匹配（COMMANDS 只认整条消息完全相等）
COMMAND_PATTERNS = {
    r"^/ping(?:\s+(.*))?$": cmd_ping,
}

PATTERN_HELP = {
    r"^/ping(?:\s+(.*))?$": "/ping [次数]",
}
