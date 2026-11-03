

import time
from typing import Optional
from config import load_feature_config

MAX_TIMES = 10
USAGE = "用法：/ping [次数]，次数范围 1~10"
API_ACTION = "get_login_info"

def parse_times(text: str) -> Optional[int]:
    arg = text[len("/ping"):].strip()
    if arg == "":
        return 1
    if arg.isdigit() and 1 <= int(arg) <= MAX_TIMES:
        return int(arg)
    return None

async def _measure(bot) -> int:
    start = time.perf_counter()
    
    await bot._api_call(API_ACTION, {}) 
    cost_ms = (time.perf_counter() - start) * 1000
    return int(cost_ms)

async def cmd_ping(bot, group_id, user_id, text):
    # 未启用时静默退出
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

COMMAND_PATTERNS = {
    r"^/ping(?:\s+(.*))?$": cmd_ping
}
