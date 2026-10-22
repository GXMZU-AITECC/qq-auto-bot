from config import load_feature_config

async def cmd_ping(bot, group_id, user_id,text):
    # 读取配置
    config = load_feature_config("ping")
    
    # 判断开关
    if not config or not config.get("enabled", False):
        return None # 开关关闭时静默退出
        
    # 正常返回
    return "pong 🏓"

COMMANDS = {
    "/ping": cmd_ping
}
