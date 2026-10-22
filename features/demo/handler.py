from config import load_feature_config


async def _demo(bot, group_id, user_id, text):
    cfg = load_feature_config("demo")
    if not cfg.get("enabled", False):
        return None
    return "晚上早点睡，梦里啥都有"


# 指令不一定要带 /，"烤肠" 和 "/烤肠" 都能触发
COMMANDS = {
    "烤肠": _demo,
    }
