from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".avif"}
_REMOTE_PREFIXES = ("http://", "https://", "base64://", "data:image/")
_SPLIT_PATHS_RE = re.compile(r"[\n,;]+")
_QUOTED_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _astrbot_data_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        from astrbot.core.utils.astrbot_path import (
            get_astrbot_data_path,
            get_astrbot_root,
        )

        data = Path(get_astrbot_data_path())
        root = Path(get_astrbot_root())
        roots.extend((data, root, root / "data"))
    except Exception:
        pass
    cwd = Path.cwd()
    roots.extend((cwd, cwd / "data"))
    docker_data = Path("/AstrBot/data")
    if docker_data.exists():
        roots.append(docker_data)
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def strip_file_uri(value: str) -> str:
    text = value.strip().strip("\"'").strip()
    if text.lower().startswith("file:"):
        parsed = urlparse(text.replace("\\", "/"))
        path = unquote(parsed.path or "")
        netloc = unquote(parsed.netloc or "")
        if _WINDOWS_DRIVE_RE.match(netloc):
            text = f"{netloc}{path}"
        elif re.match(r"^/[A-Za-z]:", path):
            text = path[1:]
        else:
            text = path or netloc
    return text.replace("\\", "/")


def looks_like_local_path(value: str) -> bool:
    raw = strip_file_uri(value)
    if not raw:
        return False
    lowered = raw.lower()
    if lowered.startswith(_REMOTE_PREFIXES):
        return False
    path = Path(raw)
    if path.is_absolute():
        return True
    if _WINDOWS_DRIVE_RE.match(raw):
        return True
    if raw.startswith(("/", "\\")):
        return True
    if value.strip().lower().startswith("file:"):
        return True
    return False


def _candidate_local_paths(value: str) -> list[Path]:
    raw = strip_file_uri(value)
    if not raw:
        return []
    out: list[Path] = [Path(raw)]
    if _WINDOWS_DRIVE_RE.match(raw):
        out.append(Path(raw[2:]))

    suffix = None
    marker = "/data/"
    idx = raw.lower().rfind(marker)
    if idx != -1:
        suffix = raw[idx + len(marker) :]
    is_absolute_like = Path(raw).is_absolute() or _WINDOWS_DRIVE_RE.match(raw)
    for root in _astrbot_data_roots():
        if suffix:
            out.append(root / suffix)
        if not is_absolute_like:
            out.append(root / raw)
            out.append(root / "workspaces" / raw)

    seen: set[str] = set()
    unique: list[Path] = []
    for path in out:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def resolve_existing_local_image(value: str) -> str | None:
    for path in _candidate_local_paths(value):
        try:
            if path.is_file():
                return str(path)
        except (OSError, ValueError):
            continue
    return None


def parse_image_path_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = str(value).strip()
        if not text:
            return []
        whole = resolve_existing_local_image(text)
        if whole:
            return [whole]
        items = []
        for part in _SPLIT_PATHS_RE.split(text):
            part = part.strip().strip("\"'")
            if part:
                items.append(part)

    found: list[str] = []
    seen: set[str] = set()
    for item in items:
        resolved = resolve_existing_local_image(item)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        found.append(resolved)
    return found


def _token_looks_like_image_path(token: str) -> bool:
    raw = strip_file_uri(token)
    if not raw:
        return False
    suffix = Path(raw).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return True
    return looks_like_local_path(raw) and ("/" in raw or "\\" in token)


def split_local_image_paths_from_text(text: str) -> tuple[list[str], str]:
    """Pull existing local image paths out of free-form text.

    Returns (paths, remaining_text). Quoted paths are tried first, then
    whitespace-separated tokens that look like file paths.
    """
    if not text or not text.strip():
        return [], text

    found: list[str] = []
    seen: set[str] = set()

    def _take(candidate: str) -> bool:
        if not _token_looks_like_image_path(candidate):
            return False
        resolved = resolve_existing_local_image(candidate)
        if not resolved or resolved in seen:
            return False
        seen.add(resolved)
        found.append(resolved)
        return True

    pieces: list[str] = []
    last = 0
    for match in _QUOTED_RE.finditer(text):
        candidate = match.group(1) or match.group(2) or ""
        if _take(candidate):
            pieces.append(text[last : match.start()])
            last = match.end()
    pieces.append(text[last:])
    remaining = "".join(pieces)

    kept: list[str] = []
    for token in remaining.split():
        if _take(token):
            continue
        kept.append(token)
    cleaned = " ".join(kept).strip()
    return found, cleaned
