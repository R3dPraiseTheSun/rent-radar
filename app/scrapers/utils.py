import asyncio
import json
import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": os.getenv(
        "SCRAPER_USER_AGENT",
        "RentRadarBot/0.1 personal research project; contact: local"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip()


def parse_float(value: str | int | float | dict | list | None) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, dict):
        preferred_keys = [
            "value",
            "amount",
            "price",
            "rent",
            "rawValue",
            "displayValue",
            "number",
        ]

        for key in preferred_keys:
            if key in value:
                parsed = parse_float(value.get(key))
                if parsed is not None:
                    return parsed

        return None

    if isinstance(value, list):
        for item in value:
            parsed = parse_float(item)
            if parsed is not None:
                return parsed
        return None

    if not isinstance(value, str):
        return None

    value = value.replace("\xa0", " ")
    value = value.replace(".", "")
    value = value.replace(",", ".")

    match = re.search(r"(\d+(?:\.\d+)?)", value)

    if not match:
        return None

    return float(match.group(1))


def parse_int(value: str | int | float | dict | list | None) -> int | None:
    number = parse_float(value)
    if number is None:
        return None
    return int(number)


def absolutize_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url, href)


def extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    results = []

    for script in soup.select('script[type="application/ld+json"]'):
        text = script.string or script.get_text(strip=True)
        if not text:
            continue

        try:
            parsed = json.loads(text)
        except Exception:
            continue

        if isinstance(parsed, list):
            results.extend([item for item in parsed if isinstance(item, dict)])
        elif isinstance(parsed, dict):
            results.append(parsed)

    return results


def extract_next_data(soup: BeautifulSoup) -> dict[str, Any] | None:
    script = soup.select_one("script#__NEXT_DATA__")
    if not script:
        return None

    text = script.string or script.get_text(strip=True)

    try:
        return json.loads(text)
    except Exception:
        return None


def recursive_find_values(obj: Any, keys: set[str]) -> list[Any]:
    found = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys:
                found.append(value)
            found.extend(recursive_find_values(value, keys))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(recursive_find_values(item, keys))

    return found


def recursive_find_dicts_with_keys(obj: Any, required_keys: set[str]) -> list[dict[str, Any]]:
    found = []

    if isinstance(obj, dict):
        if required_keys.issubset(set(obj.keys())):
            found.append(obj)

        for value in obj.values():
            found.extend(recursive_find_dicts_with_keys(value, required_keys))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(recursive_find_dicts_with_keys(item, required_keys))

    return found

def detect_currency(text: str | None, fallback: str = "EUR") -> str:
    if not text:
        return fallback

    lower = text.lower()

    if "ron" in lower or "lei" in lower or " leu" in lower:
        return "RON"

    if "eur" in lower or "euro" in lower or "€" in lower:
        return "EUR"

    return fallback

def is_probable_listing_image(url: str | None) -> bool:
    if not url:
        return False

    lower = url.lower()

    blocked = [
        "logo",
        "favicon",
        "sprite",
        "placeholder",
        "avatar",
        "profile",
        "facebook",
        "google",
        "apple",
        "staticmap",
        "map",
        "icon",
        "banner",
        "advert",
        "ads",
        "tracking",
    ]

    if any(x in lower for x in blocked):
        return False

    if not lower.startswith("http"):
        return False

    image_like = [".jpg", ".jpeg", ".png", ".webp", "cloudinary", "img", "image"]
    return any(x in lower for x in image_like)


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    out = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)

    return out

class RobotsGuard:
    def __init__(self, base_url: str, user_agent: str):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.parser = RobotFileParser()
        self.loaded = False

    async def load(self):
        robots_url = f"{self.base_url}/robots.txt"

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True) as client:
            response = await client.get(robots_url)

        self.parser.parse(response.text.splitlines())
        self.loaded = True

    async def can_fetch(self, url: str) -> bool:
        if not self.loaded:
            await self.load()

        return self.parser.can_fetch(self.user_agent, url)


class PoliteHttpClient:
    def __init__(self, base_url: str, rate_limit_seconds: float = 3):
        self.base_url = base_url.rstrip("/")
        self.rate_limit_seconds = rate_limit_seconds
        self.headers = DEFAULT_HEADERS
        self.user_agent = self.headers["User-Agent"]
        self.robots = RobotsGuard(self.base_url, self.user_agent)

    async def get_html(self, url: str) -> str | None:
        allowed = await self.robots.can_fetch(url)

        if not allowed:
            print(f"[robots] blocked, skipping: {url}")
            return None

        await asyncio.sleep(self.rate_limit_seconds)

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=25,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)

        if str(response.url) != url:
            print(f"[http] redirected: {url} -> {response.url}")

        if response.status_code >= 400:
            print(f"[http] {response.status_code}, skipping: {url}")
            return None

        return response.text


def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower()