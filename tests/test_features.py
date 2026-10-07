"""功能自动发现：每个 features 子包的 handler 都必须能被直接导入。

discover() 会吞掉导入异常只打日志，这里直接 import 让 CI 在导入失败时报错。
"""

import importlib
import pkgutil

import features


def _feature_packages() -> list[str]:
    return [m.name for m in pkgutil.iter_modules(features.__path__) if m.ispkg]


def test_存在功能子包():
    assert _feature_packages(), "features/ 下没有发现任何功能子包"


def test_每个功能子包都能导入():
    for name in _feature_packages():
        importlib.import_module(f"features.{name}.handler")
