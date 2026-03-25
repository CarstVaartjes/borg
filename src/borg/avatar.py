"""Fetch GitHub avatars and convert to Braille art."""
from __future__ import annotations

import hashlib
import re
import subprocess
from functools import lru_cache
from io import BytesIO

import httpx

# Braille dot positions: each char is a 2x4 grid
# Dot numbering:  1 4
#                 2 5
#                 3 6
#                 7 8
_BRAILLE_BASE = 0x2800
_BRAILLE_DOTS = [
    (0, 0, 0x01), (1, 0, 0x02), (2, 0, 0x04),
    (0, 1, 0x08), (1, 1, 0x10), (2, 1, 0x20),
    (3, 0, 0x40), (3, 1, 0x80),
]


def _get_gh_token() -> str | None:
    """Read GitHub token, or None if unavailable."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return None


def _extract_github_username(email: str) -> str | None:
    """Extract GitHub username from noreply email pattern."""
    match = re.match(r"\d+\+(.+)@users\.noreply\.github\.com", email)
    if match:
        return match.group(1)
    return None


@lru_cache(maxsize=64)
def fetch_avatar_url(emails: tuple[str, ...]) -> str | None:
    """Find a GitHub avatar URL from a list of emails.

    Tries: 1) GitHub username from noreply email, 2) GitHub search by email,
    3) Gravatar fallback.
    """
    token = _get_gh_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # 1. Try GitHub username from noreply emails
    for email in emails:
        username = _extract_github_username(email)
        if username and token:
            try:
                resp = httpx.get(
                    f"https://api.github.com/users/{username}",
                    headers=headers, timeout=5.0,
                )
                if resp.status_code == 200:
                    avatar_url = resp.json().get("avatar_url")
                    if avatar_url:
                        return avatar_url + "&s=256"
            except Exception:
                pass

    # 2. Try GitHub search by email
    if token:
        for email in emails:
            if "@" not in email or "noreply" in email:
                continue
            try:
                resp = httpx.get(
                    f"https://api.github.com/search/users?q={email}+in:email",
                    headers=headers, timeout=5.0,
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if items:
                        avatar_url = items[0].get("avatar_url")
                        if avatar_url:
                            return avatar_url + "&s=256"
            except Exception:
                pass

    # 3. Gravatar fallback
    for email in emails:
        if "@" in email and "noreply" not in email:
            email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
            return f"https://www.gravatar.com/avatar/{email_hash}?s=256&d=identicon"

    return None


@lru_cache(maxsize=64)
def image_to_ascii(url: str, width: int = 30, height: int = 15) -> str:
    """Download an image and convert to Braille dot art.

    Each Braille character represents a 2x4 pixel grid, giving very high
    resolution in the terminal. The result has width/2 characters per line
    and height/4 lines.

    Args:
        url: Image URL to download.
        width: Pixel width (will use width*2 actual pixels).
        height: Character height (will use height*4 actual pixels).

    Returns:
        Multi-line Braille art string.
    """
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        image_bytes = resp.content
    except Exception:
        return _name_art("?")

    try:
        from PIL import Image, ImageEnhance, ImageFilter

        img = Image.open(BytesIO(image_bytes)).convert("L")
        img = img.filter(ImageFilter.SHARPEN)
        img = ImageEnhance.Contrast(img).enhance(1.4)

        # Braille: 2 dots wide, 4 dots tall per character
        px_w = width * 2
        px_h = height * 4
        img = img.resize((px_w, px_h))
        pixels = list(img.getdata())

        # Compute threshold (median brightness)
        threshold = sorted(pixels)[len(pixels) // 2]

        def is_dark(row: int, col: int) -> bool:
            if row >= px_h or col >= px_w:
                return False
            return pixels[row * px_w + col] < threshold

        lines = []
        for char_row in range(0, px_h, 4):
            line = ""
            for char_col in range(0, px_w, 2):
                code = _BRAILLE_BASE
                for dy, dx, dot in _BRAILLE_DOTS:
                    if is_dark(char_row + dy, char_col + dx):
                        code |= dot
                line += chr(code)
            lines.append(line)
        return "\n".join(lines)
    except ImportError:
        return _name_art("SKYNET\nEMPLOYEE")


def _name_art(name: str) -> str:
    """Generate simple framed text art as fallback."""
    lines = name.split("\n")
    max_len = max(len(l) for l in lines)
    border = "+" + "-" * (max_len + 2) + "+"
    result = [border]
    for line in lines:
        result.append(f"| {line:^{max_len}} |")
    result.append(border)
    return "\n".join(result)


def get_ascii_avatar(emails: list[str], width: int = 30, height: int = 15) -> str:
    """Get Braille art avatar for an author.

    Args:
        emails: List of the author's email addresses.
        width: Character width of output.
        height: Character height of output.

    Returns:
        Braille art string.
    """
    url = fetch_avatar_url(tuple(emails))
    if url:
        return image_to_ascii(url, width, height)
    return _name_art("SKYNET\nEMPLOYEE")
