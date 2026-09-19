import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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

    aiohttp_mod = types.ModuleType("aiohttp")

    class DummyClientTimeout:
        def __init__(self, total=None):
            self.total = total

    class DummyClientSession:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("ClientSession should not be used for local images")

    aiohttp_mod.ClientTimeout = DummyClientTimeout
    aiohttp_mod.ClientSession = DummyClientSession
    sys.modules.setdefault("aiohttp", aiohttp_mod)

    core_mod = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
    message_mod = sys.modules.setdefault(
        "astrbot.core.message", types.ModuleType("astrbot.core.message")
    )
    components_mod = types.ModuleType("astrbot.core.message.components")

    class At:
        pass

    class Image:
        def __init__(self, *, file=None, url=None, raw=None):
            self.file = file
            self.url = url
            self.raw = raw

    class Reply:
        def __init__(self, chain=None):
            self.chain = chain or []

    components_mod.At = At
    components_mod.Image = Image
    components_mod.Reply = Reply
    sys.modules["astrbot.core.message.components"] = components_mod
    setattr(message_mod, "components", components_mod)
    setattr(core_mod, "message", message_mod)

    platform_mod = sys.modules.setdefault(
        "astrbot.core.platform", types.ModuleType("astrbot.core.platform")
    )

    class AstrMessageEvent:
        pass

    platform_mod.AstrMessageEvent = AstrMessageEvent

    sources_mod = sys.modules.setdefault(
        "astrbot.core.platform.sources",
        types.ModuleType("astrbot.core.platform.sources"),
    )
    aiocqhttp_pkg = sys.modules.setdefault(
        "astrbot.core.platform.sources.aiocqhttp",
        types.ModuleType("astrbot.core.platform.sources.aiocqhttp"),
    )
    event_mod = types.ModuleType(
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event"
    )

    class AiocqhttpMessageEvent:
        pass

    event_mod.AiocqhttpMessageEvent = AiocqhttpMessageEvent
    sys.modules[
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event"
    ] = event_mod
    setattr(aiocqhttp_pkg, "aiocqhttp_message_event", event_mod)
    setattr(sources_mod, "aiocqhttp", aiocqhttp_pkg)
    setattr(platform_mod, "sources", sources_mod)


_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

_install_test_stubs()

from astrbot.core.message.components import Image, Reply

from core.image_paths import (
    parse_image_path_list,
    resolve_existing_local_image,
    split_local_image_paths_from_text,
)
from core.utils import collect_publish_images, get_image_urls

_QZONE_UTILS_PATH = Path(__file__).parents[1] / "core" / "qzone" / "utils.py"
_QZONE_UTILS_SPEC = importlib.util.spec_from_file_location(
    "qzone_image_utils", _QZONE_UTILS_PATH
)
assert _QZONE_UTILS_SPEC and _QZONE_UTILS_SPEC.loader
_QZONE_UTILS_MODULE = importlib.util.module_from_spec(_QZONE_UTILS_SPEC)
_QZONE_UTILS_SPEC.loader.exec_module(_QZONE_UTILS_MODULE)
normalize_images = _QZONE_UTILS_MODULE.normalize_images


class FakeEvent:
    def __init__(self, messages, message_str=""):
        self._messages = messages
        self.message_str = message_str

    def get_messages(self):
        return self._messages


class ImageUtilsTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_local_image_path_is_extracted_and_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir, "test.png")
            image_bytes = b"fake-image-bytes"
            image_path.write_bytes(image_bytes)
            event = FakeEvent([Image(file=str(image_path), url=str(image_path))])

            sources = await get_image_urls(event)
            normalized = await normalize_images(sources)

        self.assertEqual(sources, [str(image_path)])
        self.assertEqual(normalized, [image_bytes])

    async def test_replied_local_image_path_is_extracted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir, "reply.jpg")
            image_path.write_bytes(b"reply-image")
            event = FakeEvent([Reply([Image(file=str(image_path))])])

            sources = await get_image_urls(event)

        self.assertEqual(sources, [str(image_path)])

    async def test_missing_local_image_is_not_downloaded_as_url(self):
        missing_path = Path(tempfile.gettempdir(), "missing-qzone-image.png").resolve()

        normalized = await normalize_images([str(missing_path)])

        self.assertEqual(normalized, [])

    async def test_file_uri_local_image_is_extracted_and_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir, "uri.png")
            image_bytes = b"uri-image"
            image_path.write_bytes(image_bytes)
            file_uri = image_path.resolve().as_uri()
            event = FakeEvent([Image(file=file_uri)])

            sources = await get_image_urls(event)
            normalized = await normalize_images(sources)
            self.assertEqual(len(sources), 1)
            self.assertTrue(Path(sources[0]).is_file())
            self.assertEqual(Path(sources[0]).resolve(), image_path.resolve())

        self.assertEqual(normalized, [image_bytes])

    async def test_data_relative_windows_path_is_mapped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            image_path = data_root / "workspaces" / "u" / "pic.png"
            image_path.parent.mkdir(parents=True)
            image_bytes = b"mapped-image"
            image_path.write_bytes(image_bytes)
            with patch(
                "core.image_paths._astrbot_data_roots", return_value=[data_root]
            ):
                resolved = resolve_existing_local_image(
                    r"\AstrBot\data\workspaces\u\pic.png"
                )
                parsed = parse_image_path_list(
                    r"E:\0QQBot\AstrBot\data\workspaces\u\pic.png"
                )
                normalized = await normalize_images(
                    [r"\AstrBot\data\workspaces\u\pic.png"]
                )

        self.assertEqual(Path(resolved), image_path)
        self.assertEqual(parsed, [str(image_path)])
        self.assertEqual(normalized, [image_bytes])

    async def test_text_local_path_is_split_from_caption(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir, "caption.png")
            image_path.write_bytes(b"caption")
            paths, cleaned = split_local_image_paths_from_text(
                f'今天天气真好 "{image_path}"'
            )

        self.assertEqual(paths, [str(image_path)])
        self.assertEqual(cleaned, "今天天气真好")

    async def test_collect_publish_images_reads_extra_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir, "extra.png")
            image_path.write_bytes(b"extra")
            event = FakeEvent([])

            images, cleaned = await collect_publish_images(
                event,
                text="配图",
                extra_paths=str(image_path),
                get_image=False,
            )

        self.assertEqual(images, [str(image_path)])
        self.assertEqual(cleaned, "配图")

    async def test_prefer_existing_local_file_over_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir, "prefer.png")
            image_path.write_bytes(b"prefer")
            event = FakeEvent(
                [
                    Image(
                        file=str(image_path),
                        url="http://127.0.0.1:6099/cache/prefer.png",
                    )
                ]
            )

            sources = await get_image_urls(event)

        self.assertEqual(sources, [str(image_path)])


if __name__ == "__main__":
    unittest.main()
