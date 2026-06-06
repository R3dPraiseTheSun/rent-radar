import re
import asyncio
import os
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseRentScraper
from app.scrapers.utils import (
    PoliteHttpClient,
    absolutize_url,
    clean_text,
    extract_json_ld,
    extract_next_data,
    parse_float,
    parse_int,
    recursive_find_dicts_with_keys,
    recursive_find_values,
)


class StoriaScraper(BaseRentScraper):
    source_name = "storia_ro"

    def __init__(
        self,
        base_url: str = "https://www.storia.ro",
        city_slug: str = "iasi",
        max_pages: int = 3,
        rate_limit_seconds: float = 4,
    ):
        self.base_url = base_url.rstrip("/")
        self.city_slug = city_slug
        self.max_pages = max_pages
        self.client = PoliteHttpClient(
            base_url=self.base_url,
            rate_limit_seconds=rate_limit_seconds,
        )

    def build_search_url(self, page: int) -> str:
        # Storia URL structures may change. This is intentionally isolated.
        # If this does not return results, only update this method.
        if page <= 1:
            return f"{self.base_url}/ro/rezultate/inchiriere/apartament/{self.city_slug}"
        return f"{self.base_url}/ro/rezultate/inchiriere/apartament/{self.city_slug}?page={page}"

    async def search_listing_urls(self, city: str, zones: list[str]) -> list[str]:
        urls: set[str] = set()

        for page in range(1, self.max_pages + 1):
            search_url = self.build_search_url(page)
            html = await self.client.get_html(search_url)

            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")

            for a in soup.select("a[href]"):
                href = a.get("href")
                full_url = absolutize_url(self.base_url, href)

                if not full_url:
                    continue

                full_url = self.strip_tracking(full_url)

                if self.looks_like_listing_url(full_url):
                    urls.add(full_url)

            print(f"[storia] page={page}, urls_so_far={len(urls)}")

        return sorted(urls)

    @staticmethod
    def strip_tracking(url: str) -> str:
        url = url.split("?")[0].split("#")[0]

        # Some search-result links may use /hpr/ as a redirect/tracking prefix.
        # Convert to canonical listing path.
        url = url.replace("https://www.storia.ro/hpr/ro/oferta/", "https://www.storia.ro/ro/oferta/")
        url = url.replace("http://www.storia.ro/hpr/ro/oferta/", "https://www.storia.ro/ro/oferta/")

        return url

    @staticmethod
    def looks_like_listing_url(url: str) -> bool:
        blocked_parts = [
            "/login",
            "/oferta/contact",
            "/plata",
            "/abuse",
            "/anunt-nou",
            "/hpr/",
            "/api/",
            "/ajax/",
        ]

        if any(part in url for part in blocked_parts):
            return False

        if "storia.ro" not in url:
            return False

        # Accept only canonical public listing pages.
        return "/ro/oferta/" in url and "-ID" in url

    @staticmethod
    def extract_currency(text: str, fallback: str = "EUR") -> str:
        from app.scrapers.utils import detect_currency
        return detect_currency(text, fallback=fallback)
    
    @staticmethod
    def extract_image_urls(value) -> list[str]:
        urls = []

        if isinstance(value, str):
            if value.startswith("http") and any(
                ext in value.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]
            ):
                urls.append(value)

        elif isinstance(value, dict):
            for nested_value in value.values():
                urls.extend(StoriaScraper.extract_image_urls(nested_value))

        elif isinstance(value, list):
            for item in value:
                urls.extend(StoriaScraper.extract_image_urls(item))

        return urls

    def extract_gallery_images(self, soup: BeautifulSoup, next_data: dict | None) -> list[str]:
        from app.scrapers.utils import is_probable_listing_image, dedupe_keep_order

        images = []

        # 1. Prefer explicit listing/gallery image elements.
        selectors = [
            'img[data-cy*="gallery"]',
            'img[data-testid*="gallery"]',
            'picture img',
            'button img',
            'figure img',
        ]

        for selector in selectors:
            for img in soup.select(selector):
                for attr in ["src", "data-src", "srcset"]:
                    value = img.get(attr)
                    if not value:
                        continue

                    if attr == "srcset":
                        parts = [p.strip().split(" ")[0] for p in value.split(",")]
                        images.extend(parts)
                    else:
                        images.append(value)

        # 2. Extract from Next data, but only URLs that look like listing photos.
        if next_data:
            possible_images = recursive_find_values(
                next_data,
                {"url", "src", "large", "medium", "small", "image", "images", "photos"},
            )

            for value in possible_images:
                images.extend(self.extract_image_urls(value))

        images = [x for x in images if is_probable_listing_image(x)]

        return dedupe_keep_order(images)


    @staticmethod
    def extract_price_from_visible_price_text(soup: BeautifulSoup) -> float | None:
        candidates = []

        for selector in [
            '[data-cy*="price"]',
            '[class*="price"]',
            '[aria-label*="price"]',
            '[aria-label*="Preț"]',
            '[aria-label*="pret"]',
        ]:
            for element in soup.select(selector):
                text = clean_text(element.get_text(" ", strip=True))
                if text:
                    candidates.append(text)

        # Prefer strings that explicitly contain currency.
        for text in candidates:
            parsed = StoriaScraper.extract_price_from_text(text)
            if parsed and 50 <= parsed <= 10000:
                return parsed

        return None


    @staticmethod
    def normalize_price_number(value: str) -> str:
        value = value.strip()

        # 1,200 or 1.200 -> 1200
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
            return value.replace(",", "").replace(".", "")

        return value

    @staticmethod
    def extract_price_from_text(text: str) -> float | None:
        if not text:
            return None

        normalized = text.replace("\xa0", " ")

        price_number = r"\d{1,3}(?:[.,]\d{3})+|\d{2,6}"

        patterns = [
            rf"(?:pret|preț|chirie|rent)[^\d]{{0,20}}({price_number})\s*(?:€|eur|euro|ron|lei|leu)",
            rf"({price_number})\s*(?:€|eur|euro|ron|lei|leu)\s*(?:/ luna|/ lună|luna|lună)?",
            rf"(?:€|eur|euro|ron|lei|leu)\s*({price_number})",
        ]

        candidates = []

        for pattern in patterns:
            for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
                parsed = parse_float(ImobiliareScraper.normalize_price_number(match.group(1)))
                if parsed and 50 <= parsed <= 50000:
                    candidates.append(parsed)

        if not candidates:
            return None

        return candidates[0]

    async def scrape_listing(self, url: str) -> dict[str, Any]:
        html = await self.client.get_html(url)

        if not html:
            return {}

        soup = BeautifulSoup(html, "lxml")

        payload = self.from_json_data(url, soup)

        if not payload.get("title"):
            payload.update(self.from_html_fallback(url, soup))

        payload["raw_json"] = {
            "source_url": url,
            "json_ld": extract_json_ld(soup),
            "next_data": extract_next_data(soup),
        }

        return payload

    def empty_payload(self, url: str) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "source_listing_id": None,
            "source_url": url,
            "title": None,
            "description": None,
            "price_eur": None,
            "currency": "EUR",
            "city": "Iasi",
            "zone": None,
            "rooms": None,
            "surface_m2": None,
            "floor": None,
            "image_urls": [],
            "raw_json": {},
        }

    def from_json_data(self, url: str, soup: BeautifulSoup) -> dict[str, Any]:
        base = self.empty_payload(url)

        json_ld = extract_json_ld(soup)
        next_data = extract_next_data(soup)

        title = None
        description = None
        price = None
        currency = "EUR"

        for item in json_ld:
            if not title:
                title = item.get("name") or item.get("headline")

            if not description:
                description = item.get("description")


            offers = item.get("offers")
            if isinstance(offers, dict):
                price = price or offers.get("price")
                currency = offers.get("priceCurrency") or currency

        if next_data:
            possible_titles = recursive_find_values(next_data, {"title", "name"})
            possible_descriptions = recursive_find_values(next_data, {"description"})
            gallery_images = self.extract_gallery_images(soup, next_data)

            if not title:
                title = self.pick_text(possible_titles)

            if not description:
                description = self.pick_text(possible_descriptions)

        text_blob = " ".join(
            [
                clean_text(title) or "",
                clean_text(description) or "",
                soup.get_text(" ", strip=True)[:5000],
            ]
        )

        base.update(
            {
                "source_listing_id": self.extract_source_id(url),
                "title": clean_text(title),
                "description": clean_text(description),
                "price_eur": (
                    self.extract_price_from_meta(soup)
                    or self.extract_price_from_json_ld(json_ld)
                    or self.extract_price_from_visible_price_text(soup)
                    or self.extract_price_from_title_or_description(title, description)
                ),
                "currency": self.extract_currency(text_blob, currency or "EUR"),
                "city": "Iasi",
                "zone": self.extract_zone(text_blob),
                "rooms": self.extract_rooms(text_blob),
                "surface_m2": self.extract_surface(text_blob),
                "floor": self.extract_floor(text_blob),
                "image_urls": gallery_images,
            }
        )

        return base

    def from_html_fallback(self, url: str, soup: BeautifulSoup) -> dict[str, Any]:
        text = soup.get_text(" ", strip=True)

        title = None

        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)

        images = self.extract_gallery_images(soup, extract_next_data(soup))

        return {
            "source": self.source_name,
            "source_listing_id": self.extract_source_id(url),
            "source_url": url,
            "title": clean_text(title),
            "description": self.extract_description_fallback(soup),
            "price_eur": self.extract_price_from_text(text),
            "currency": "EUR",
            "city": "Iasi",
            "zone": self.extract_zone(text),
            "rooms": self.extract_rooms(text),
            "surface_m2": self.extract_surface(text),
            "floor": self.extract_floor(text),
            "image_urls": sorted(set(images)),
        }

    @staticmethod
    def pick_text(values: list[Any]) -> str | None:
        for value in values:
            if isinstance(value, str) and len(value.strip()) >= 5:
                return value
        return None

    @staticmethod
    def pick_price(values: list[Any]) -> Any:
        for value in values:
            parsed = parse_float(value)
            if parsed and 50 <= parsed <= 10000:
                return parsed
        return None

    @staticmethod
    def extract_source_id(url: str) -> str | None:
        match = re.search(r"-ID([A-Za-z0-9]+)", url)
        if match:
            return match.group(1)

        match = re.search(r"/ro/oferta/([^/?#]+)", url)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def extract_price_from_text(text: str) -> float | None:
        if not text:
            return None

        normalized = text.replace("\xa0", " ")

        patterns = [
            r"(?:pret|preț|chirie|rent)[^\d]{0,20}(\d{2,5})\s*(?:€|eur|euro)",
            r"(\d{2,5})\s*(?:€|eur|euro)\s*(?:/ luna|/ lună|luna|lună)?",
            r"(?:€|eur|euro)\s*(\d{2,5})",
        ]

        candidates = []

        for pattern in patterns:
            for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
                parsed = parse_float(match.group(1))
                if parsed and 50 <= parsed <= 10000:
                    candidates.append(parsed)

        if not candidates:
            return None

        # Prefer realistic Iași apartment rents.
        realistic = [x for x in candidates if 150 <= x <= 3000]
        if realistic:
            return realistic[0]

        return candidates[0]

    @staticmethod
    def extract_price_from_json_ld(json_ld: list[dict[str, Any]]) -> float | None:
        for item in json_ld:
            offers = item.get("offers")

            if isinstance(offers, dict):
                for key in ["price", "priceSpecification"]:
                    parsed = parse_float(offers.get(key))
                    if parsed and 50 <= parsed <= 10000:
                        return parsed

            if isinstance(offers, list):
                for offer in offers:
                    parsed = parse_float(offer)
                    if parsed and 50 <= parsed <= 10000:
                        return parsed

        return None

    @staticmethod
    def extract_price_from_meta(soup: BeautifulSoup) -> float | None:
        selectors = [
            'meta[property="product:price:amount"]',
            'meta[property="og:price:amount"]',
            'meta[name="price"]',
            'meta[itemprop="price"]',
        ]

        for selector in selectors:
            tag = soup.select_one(selector)
            if tag:
                value = tag.get("content")
                parsed = parse_float(value)
                if parsed and 50 <= parsed <= 10000:
                    return parsed

        return None

    @staticmethod
    def extract_rooms(text: str) -> float | None:
        patterns = [
            r"(\d+)\s*camere",
            r"(\d+)\s*camera",
            r"apartament\s+(\d+)\s*camere",
            r"garsonier[ăa]",
        ]

        if re.search(patterns[-1], text, flags=re.IGNORECASE):
            return 1

        for pattern in patterns[:-1]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return int(parse_float(match.group(1)))

        return None

    @staticmethod
    def extract_surface(text: str) -> float | None:
        patterns = [
            r"(\d+(?:[.,]\d+)?)\s*m²",
            r"(\d+(?:[.,]\d+)?)\s*mp",
            r"suprafa[țt][aă]\s*(?:util[ăa])?\s*(\d+(?:[.,]\d+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = parse_float(match.group(1))
                if value and 10 <= value <= 300:
                    return value

        return None

    @staticmethod
    def extract_floor(text: str) -> str | None:
        patterns = [
            r"etaj\s+(\d+\s*/\s*\d+)",
            r"etaj\s+(\d+)",
            r"parter",
            r"demisol",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                if match.groups():
                    return clean_text(match.group(1))
                return match.group(0).lower()

        return None

    @staticmethod
    def extract_zone(text: str) -> str | None:
        zones = [
            "Copou",
            "Tatarasi",
            "Tătărași",
            "Podu Ros",
            "Podu Roș",
            "Nicolina",
            "Pacurari",
            "Păcurari",
            "Alexandru cel Bun",
            "Centru",
            "CUG",
            "Moara de Vant",
            "Moara de Vânt",
            "Dacia",
            "Galata",
            "Bucium",
            "Frumoasa",
            "Mircea cel Batran",
            "Mircea cel Bătrân",
        ]

        lowered = text.lower()

        for zone in zones:
            if zone.lower() in lowered:
                return zone

        return None

    @staticmethod
    def extract_description_fallback(soup: BeautifulSoup) -> str | None:
        candidates = []

        for selector in [
            '[data-cy*="description"]',
            '[class*="description"]',
            "section",
            "article",
        ]:
            for element in soup.select(selector):
                text = clean_text(element.get_text(" ", strip=True))
                if text and len(text) > 80:
                    candidates.append(text)

        if candidates:
            return max(candidates, key=len)[:5000]

        return None