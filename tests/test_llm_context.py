import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from core.llm_context import inject_image_urls, normalize_context_image_url


class LlmContextTests(unittest.TestCase):
    def test_protocol_relative_url_is_normalized(self):
        self.assertEqual(
            normalize_context_image_url("//qzonestyle.gtimg.cn/a.jpg"),
            "https://qzonestyle.gtimg.cn/a.jpg",
        )

    def test_inject_into_request_appends_unique_urls(self):
        req = SimpleNamespace(image_urls=["https://already.example/a.jpg"])
        injected = inject_image_urls(
            req,
            [
                "https://already.example/a.jpg",
                " https://qzone.example/b.jpg ",
                "//qzone.example/c.jpg",
                "",
            ],
        )
        self.assertTrue(injected)
        self.assertEqual(
            req.image_urls,
            [
                "https://already.example/a.jpg",
                "https://qzone.example/b.jpg",
                "https://qzone.example/c.jpg",
            ],
        )

    def test_missing_request_is_silent(self):
        self.assertFalse(inject_image_urls(None, ["https://qzone.example/a.jpg"]))
        self.assertFalse(inject_image_urls(object(), ["https://qzone.example/a.jpg"]))

    def test_none_image_list_on_request_is_initialized(self):
        req = SimpleNamespace(image_urls=None)
        self.assertTrue(inject_image_urls(req, ["https://qzone.example/a.jpg"]))
        self.assertEqual(req.image_urls, ["https://qzone.example/a.jpg"])


if __name__ == "__main__":
    unittest.main()
