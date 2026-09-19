import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pathlib import Path


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

    event_mod = sys.modules.setdefault(
        "astrbot.api.event", types.ModuleType("astrbot.api.event")
    )

    class MessageChain:
        def __init__(self):
            self.chain = []

        def message(self, text):
            self.chain.append(text)
            return self

    event_mod.MessageChain = MessageChain
    setattr(api_mod, "event", event_mod)

    core_mod = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
    message_mod = sys.modules.setdefault(
        "astrbot.core.message", types.ModuleType("astrbot.core.message")
    )
    components_mod = types.ModuleType("astrbot.core.message.components")

    class Plain:
        def __init__(self, text):
            self.text = text

    components_mod.Plain = Plain
    sys.modules["astrbot.core.message.components"] = components_mod
    setattr(message_mod, "components", components_mod)

    platform_mod = sys.modules.setdefault(
        "astrbot.core.platform", types.ModuleType("astrbot.core.platform")
    )
    event_platform_mod = types.ModuleType("astrbot.core.platform.astr_message_event")

    class AstrMessageEvent:
        pass

    event_platform_mod.AstrMessageEvent = AstrMessageEvent
    sys.modules["astrbot.core.platform.astr_message_event"] = event_platform_mod
    setattr(platform_mod, "astr_message_event", event_platform_mod)

    star_mod = sys.modules.setdefault(
        "astrbot.core.star", types.ModuleType("astrbot.core.star")
    )
    context_mod = types.ModuleType("astrbot.core.star.context")

    class Context:
        pass

    context_mod.Context = Context
    sys.modules["astrbot.core.star.context"] = context_mod
    setattr(star_mod, "context", context_mod)
    setattr(core_mod, "message", message_mod)
    setattr(core_mod, "platform", platform_mod)
    setattr(core_mod, "star", star_mod)


_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

_install_test_stubs()

from core.sender import (  # noqa: E402
    SenderLite,
    build_post_chain,
    normalize_feedback_session,
)


class FakePost:
    def to_str(self) -> str:
        return "说说正文"


class ReceiptTests(unittest.IsolatedAsyncioTestCase):
    def test_empty_session_is_normalized_to_blank(self):
        self.assertEqual(normalize_feedback_session(None), "")
        self.assertEqual(normalize_feedback_session("  "), "")
        self.assertEqual(
            normalize_feedback_session(" aiocqhttp:FriendMessage:123 "),
            "aiocqhttp:FriendMessage:123",
        )

    def test_build_post_chain_includes_message(self):
        chain = build_post_chain(FakePost(), message="已发布")
        self.assertEqual([item.text for item in chain], ["已发布", "说说正文"])

    async def test_blank_session_is_silent(self):
        context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        sender = SenderLite(context)
        event = SimpleNamespace(send=AsyncMock())

        sent = await sender.send_llm_receipt("  ", FakePost(), message="已发布")

        self.assertFalse(sent)
        context.send_message.assert_not_called()
        event.send.assert_not_called()

    async def test_configured_session_sends_receipt(self):
        context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        sender = SenderLite(context)

        sent = await sender.send_llm_receipt(
            "aiocqhttp:FriendMessage:123456",
            FakePost(),
            message="已点赞",
        )

        self.assertTrue(sent)
        context.send_message.assert_awaited_once()
        session, chain = context.send_message.await_args.args
        self.assertEqual(session, "aiocqhttp:FriendMessage:123456")
        self.assertEqual(chain.chain, ["已点赞", "说说正文"])

    async def test_send_failure_is_swallowed(self):
        context = SimpleNamespace(
            send_message=AsyncMock(side_effect=ValueError("bad session"))
        )
        sender = SenderLite(context)

        sent = await sender.send_llm_receipt(
            "not-a-session",
            FakePost(),
            message="已发布",
        )

        self.assertFalse(sent)


if __name__ == "__main__":
    unittest.main()
