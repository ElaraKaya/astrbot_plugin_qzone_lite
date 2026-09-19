from __future__ import annotations

from astrbot.core.message.components import Image, Reply
from astrbot.core.platform import AstrMessageEvent

from .image_paths import (
    looks_like_local_path,
    parse_image_path_list,
    resolve_existing_local_image,
    split_local_image_paths_from_text,
)

SUPPORTED_IMAGE_PROTOCOLS = ("http://", "https://", "base64://", "data:image/")


def _iter_image_candidates(seg: Image) -> list[str]:
    candidates: list[str] = []
    for key in ("path", "file", "url", "src", "data_url"):
        value = getattr(seg, key, None)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    raw = getattr(seg, "raw", None)
    if isinstance(raw, dict):
        for key in ("path", "file", "url", "src"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
    return candidates


def _extract_image_source(seg: Image) -> str | None:
    local_fallback = None
    remote_fallback = None
    for value in _iter_image_candidates(seg):
        existing = resolve_existing_local_image(value)
        if existing:
            return existing
        if looks_like_local_path(value):
            local_fallback = local_fallback or value
            continue
        if value.startswith("data:image/"):
            if ";base64," in value:
                remote_fallback = remote_fallback or value
            continue
        if value.startswith(SUPPORTED_IMAGE_PROTOCOLS):
            remote_fallback = remote_fallback or value
    return local_fallback or remote_fallback


async def _resolve_image_source(seg: Image) -> str | None:
    source = _extract_image_source(seg)
    if source:
        existing = resolve_existing_local_image(source)
        if existing:
            return existing
        if looks_like_local_path(source) or source.startswith(
            (*SUPPORTED_IMAGE_PROTOCOLS, "data:image/")
        ):
            return source

    convert = getattr(seg, "convert_to_file_path", None)
    if callable(convert):
        try:
            local = await convert()
        except Exception:
            local = None
        if isinstance(local, str) and local.strip():
            existing = resolve_existing_local_image(local.strip())
            if existing:
                return existing
    return source


async def get_image_urls(
    event: AstrMessageEvent,
    reply: bool = True,
    extra_paths: str | list[str] | None = None,
) -> list[str]:
    chain = event.get_messages()
    images: list[str] = []
    images.extend(parse_image_path_list(extra_paths))
    if reply:
        reply_seg = next((seg for seg in chain if isinstance(seg, Reply)), None)
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Image):
                    source = await _resolve_image_source(seg)
                    if source:
                        images.append(source)
    for seg in chain:
        if isinstance(seg, Image):
            source = await _resolve_image_source(seg)
            if source:
                images.append(source)
    return list(dict.fromkeys(images))


async def collect_publish_images(
    event: AstrMessageEvent,
    *,
    text: str = "",
    extra_paths: str | list[str] | None = None,
    get_image: bool = True,
) -> tuple[list[str], str]:
    from_text, cleaned = split_local_image_paths_from_text(text)
    images: list[str] = []
    images.extend(parse_image_path_list(extra_paths))
    images.extend(from_text)
    if get_image:
        images.extend(await get_image_urls(event))
    return list(dict.fromkeys(images)), cleaned
