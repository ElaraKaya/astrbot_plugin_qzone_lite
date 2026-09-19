from __future__ import annotations

from typing import Any


def normalize_context_image_url(url: str) -> str:
    text = (url or "").strip()
    if text.startswith("//"):
        return "https:" + text
    return text


def inject_image_urls(req: Any, images: list[str] | None) -> bool:
    if req is None or not hasattr(req, "image_urls"):
        return False
    urls = req.image_urls
    if urls is None:
        urls = []
        req.image_urls = urls
    seen = set(urls)
    has_any = False
    for raw in images or []:
        if not isinstance(raw, str):
            continue
        url = normalize_context_image_url(raw)
        if not url:
            continue
        has_any = True
        if url in seen:
            continue
        urls.append(url)
        seen.add(url)
    return has_any
