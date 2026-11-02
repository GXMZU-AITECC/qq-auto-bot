from config import load_feature_config

async def cmd_morning(bot, group_id, user_id, text):
    # 1. 读取配置 (为了和别人保持统一，这里写 morning)
    config = load_feature_config("morning")
    
    # 2. 判断开关 (如果没有配置默认关闭，你可以去 configs 里加一个，或者暂时先不管)
    if not config or not config.get("enabled", False):
        return None

    # 3. 正常返回早安问候
    return "早安呀！今天也要充满活力哦~ ☀️"

# 4. 导出模糊匹配字典 (注意这里用的是 COMMAND_PATTERNS)
COMMAND_PATTERNS = {
    r"^早安": cmd_morning
}
