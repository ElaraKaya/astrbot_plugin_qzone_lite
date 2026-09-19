import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


def _install_test_stubs() -> None:
    logger = SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )

    astrbot_pkg = sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
    api_mod = sys.modules.setdefault("astrbot.api", types.ModuleType("astrbot.api"))
    api_mod.logger = logger
    setattr(astrbot_pkg, "api", api_mod)

    aiocqhttp_mod = sys.modules.setdefault("aiocqhttp", types.ModuleType("aiocqhttp"))
    aiocqhttp_mod.CQHttp = object

    core_mod = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
    config_pkg = sys.modules.setdefault(
        "astrbot.core.config", types.ModuleType("astrbot.core.config")
    )
    astrbot_config_mod = types.ModuleType("astrbot.core.config.astrbot_config")

    class AstrBotConfig(dict):
        def save_config(self):
            return None

    astrbot_config_mod.AstrBotConfig = AstrBotConfig
    sys.modules["astrbot.core.config.astrbot_config"] = astrbot_config_mod
    setattr(config_pkg, "astrbot_config", astrbot_config_mod)

    star_mod = sys.modules.setdefault(
        "astrbot.core.star", types.ModuleType("astrbot.core.star")
    )
    context_mod = types.ModuleType("astrbot.core.star.context")

    class Context:
        pass

    context_mod.Context = Context
    sys.modules["astrbot.core.star.context"] = context_mod
    setattr(star_mod, "context", context_mod)
    setattr(core_mod, "config", config_pkg)
    setattr(core_mod, "star", star_mod)


_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

_install_test_stubs()

from core.config import ConfigNode  # noqa: E402


class SampleConfig(ConfigNode):
    name: str
    enabled: bool = True
    session_id: str = ""
    count: int = 50


class ConfigNodeTests(unittest.TestCase):
    def test_class_default_does_not_shadow_stored_session(self):
        cfg = SampleConfig(
            {
                "name": "qzone",
                "session_id": "珂夜QQ:GroupMessage:1059513166",
            }
        )
        self.assertEqual(cfg.session_id, "珂夜QQ:GroupMessage:1059513166")
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.count, 50)

    def test_false_bool_is_not_replaced_by_class_default(self):
        cfg = SampleConfig({"name": "qzone", "enabled": False, "count": 0})
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.count, 0)

    def test_setattr_writes_through_to_data(self):
        cfg = SampleConfig({"name": "qzone"})
        cfg.session_id = "aiocqhttp:FriendMessage:123"
        self.assertEqual(cfg.session_id, "aiocqhttp:FriendMessage:123")
        self.assertEqual(cfg._data["session_id"], "aiocqhttp:FriendMessage:123")


if __name__ == "__main__":
    unittest.main()
