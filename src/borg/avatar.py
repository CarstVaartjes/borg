"""Fetch GitHub avatars and convert to ASCII art."""
from __future__ import annotations

import hashlib
import re
import subprocess
from functools import lru_cache
from io import BytesIO

import httpx

# Grayscale thresholds for half-block rendering
_DARK = 100   # below = dark
_LIGHT = 155  # above = light


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
    # Pattern: 12345+username@users.noreply.github.com
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

    # 2. Try GitHub search by email (finds users by their commit email)
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
            return f"https://www.gravatar.com/avatar/{email_hash}?s=64&d=identicon"

    return None


@lru_cache(maxsize=64)
def image_to_ascii(url: str, width: int = 30, height: int = 15) -> str:
    """Download an image and convert to half-block art.

    Uses Unicode half-block characters (▀▄█ ) to pack 2 vertical pixels
    per character cell, doubling the effective vertical resolution.

    Args:
        url: Image URL to download.
        width: Art width in characters.
        height: Art height in character rows (each row = 2 pixels).

    Returns:
        Multi-line string.
    """
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        image_bytes = resp.content
    except Exception:
        return _name_art("?")

    try:
        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("L")
        # Double the pixel height since we pack 2 rows per character
        pixel_h = height * 2
        img = img.resize((width, pixel_h))
        pixels = list(img.getdata())

        def px(row: int, col: int) -> int:
            if row >= pixel_h:
                return 255  # treat out-of-bounds as white
            return pixels[row * width + col]

        lines = []
        for row in range(0, pixel_h, 2):
            line = ""
            for col in range(width):
                top = px(row, col)
                bot = px(row + 1, col)
                top_dark = top < _DARK
                bot_dark = bot < _DARK
                top_light = top > _LIGHT
                bot_light = bot > _LIGHT

                if top_dark and bot_dark:
                    line += "█"
                elif top_dark and not bot_dark:
                    line += "▀"
                elif not top_dark and bot_dark:
                    line += "▄"
                elif top_light and bot_light:
                    line += " "
                elif top < bot:
                    line += "▀"
                elif top > bot:
                    line += "▄"
                else:
                    line += "░"
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
    """Get ASCII art avatar for an author.

    Args:
        emails: List of the author's email addresses.
        width: ASCII width.
        height: ASCII height.

    Returns:
        ASCII art string.
    """
    url = fetch_avatar_url(tuple(emails))
    if url:
        return image_to_ascii(url, width, height)
    return _name_art("SKYNET\nEMPLOYEE")
