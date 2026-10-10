import os
import yaml

_config = None


def _load():
    global _config
    path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)


def get(*keys, default=None):
    """按层级取值，如 get('llonebot', 'ws_url')"""
    if _config is None:
        _load()
    val = _config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default


def load_feature_config(name: str) -> dict:
    """加载 configs/{name}.yaml；若存在 configs/{name}.local.yaml 则优先加载本地真实配置"""
    base = os.path.join(os.path.dirname(__file__), "configs")
    for fname in (f"{name}.local.yaml", f"{name}.yaml"):
        path = os.path.join(base, fname)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}
