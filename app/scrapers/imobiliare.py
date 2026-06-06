import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers.base import BaseRentScraper
from app.scrapers.utils import (
    PoliteHttpClient,
    absolutize_url,
    clean_text,
    extract_json_ld,
    extract_next_data,
    parse_float,
    recursive_find_values,
)


class ImobiliareScraper(BaseRentScraper):
    source_name = "imobiliare_ro"

    def __init__(
        self,
        base_url: str = "https://www.imobiliare.ro",
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
        # Imobiliare URL structures may change. Keep this isolated.
        if page <= 1:
            return f"{self.base_url}/inchirieri-apartamente/{self.city_slug}"
        return f"{self.base_url}/inchirieri-apartamente/{self.city_slug}?pagina={page}"

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

                if self.looks_like_listing_url(full_url):
                    urls.add(self.strip_tracking(full_url))

            print(f"[imobiliare] page={page}, urls_so_far={len(urls)}")

        return sorted(urls)

    @staticmethod
    def strip_tracking(url: str) -> str:
        return url.split("?")[0].split("#")[0]

    @staticmethod
    def looks_like_listing_url(url: str) -> bool:
        blocked_parts = [
            "/cont",
            "/login",
            "/adauga",
            "/contact",
            "/agentii",
            "/ansambluri",
            "/inchirieri-apartamente/",
        ]

        if any(part in url for part in blocked_parts):
            return False

        if "imobiliare.ro" not in url:
            return False

        # Real listing pages look like:
        # https://www.imobiliare.ro/oferta/apartament-de-inchiriat-iasi-...
        return "/oferta/" in url and "apartament-de-inchiriat" in url

    @staticmethod
    def extract_currency(text: str, fallback: str = "EUR") -> str:
        from app.scrapers.utils import detect_currency
        return detect_currency(text, fallback=fallback)


    @staticmethod
    def is_imobiliare_listing_image(url: str | None) -> bool:
        if not url:
            return False

        u = url.strip().lower()

        if not u.startswith(("http://", "https://")):
            return False

        parsed = urlparse(u)
        host = parsed.netloc
        path = parsed.path

        # Reject non-raster files and website UI assets.
        if path.endswith((".svg", ".ico")):
            return False

        if host == "assets.imobiliare.ro":
            return False

        if any(bad in u for bad in [
            "/theme/",
            "/assets/",
            "app-store",
            "logo",
            "placeholder",
            "user-placeholder",
            "agent",
            "agency",
            "avatar",
            "icon",
            "bus",
            "station",
            "airplane",
            "tram",
            "metro",
            "school",
            "hospital",
            "marker",
            "pin",
        ]):
            return False

        # Strong positive signal for real Imobiliare property photos.
        if host == "i.roamcdn.net" and "/prop/imo/" in path:
            return True

        if "prod-property-core-backend-media-imo" in u:
            return True

        return False

    @staticmethod
    def extract_image_urls(value) -> list[str]:
        urls = []

        if isinstance(value, str):
            urls.append(value)

        elif isinstance(value, dict):
            for nested_value in value.values():
                urls.extend(ImobiliareScraper.extract_image_urls(nested_value))

        elif isinstance(value, list):
            for item in value:
                urls.extend(ImobiliareScraper.extract_image_urls(item))

        return urls

    def extract_gallery_images(self, soup: BeautifulSoup, next_data: dict | None) -> list[str]:
        from app.scrapers.utils import dedupe_keep_order

        images = []

        selectors = [
            # Matches the image visible in your screenshot:
            # <img class="absolute inset-0 h-full w-full scale-110 object-cover blur-xl" ...>
            # <img class="relative h-full w-full object-contain" ...>
            "img[src*='i.roamcdn.net/prop/imo/']",
            "img[srcset*='i.roamcdn.net/prop/imo/']",
            "img[data-src*='i.roamcdn.net/prop/imo/']",

            # Gallery/container fallbacks.
            "[ref='gallery'] img",
            "[class*='gallery'] img",
            "[class*='swiper'] img",
            "img.swiper-lazy",
            "img.object-contain",
            "img.object-cover",
            "img.md\\:object-contain",
            "picture img",
            "figure img",
        ]

        for selector in selectors:
            for img in soup.select(selector):
                for attr in ["src", "data-src", "data-lazy", "data-original", "srcset"]:
                    value = img.get(attr)
                    if not value:
                        continue

                    if attr == "srcset":
                        parts = [p.strip().split(" ")[0] for p in value.split(",") if p.strip()]
                        images.extend(parts)
                    else:
                        images.append(value)

        if next_data:
            possible_images = recursive_find_values(
                next_data,
                {
                    "url",
                    "src",
                    "large",
                    "medium",
                    "small",
                    "image",
                    "images",
                    "photos",
                    "gallery",
                    "galleryImages",
                },
            )

            for value in possible_images:
                images.extend(self.extract_image_urls(value))

        images = [x for x in images if self.is_imobiliare_listing_image(x)]

        return dedupe_keep_order(images)

    @staticmethod
    def extract_listing_address(soup: BeautifulSoup) -> str | None:
        selectors = [
            '[data-cy="listing-address"]',
            '[data-testid="listing-address"]',
            '[class*="listing-address"]',
            '[class*="address"]',
            '[class*="location"]',
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = clean_text(element.get_text(" ", strip=True))
                if text:
                    return text

        # Breadcrumb fallback: useful when address element is hidden or missing.
        breadcrumb_parts = []
        for element in soup.select('nav a, [aria-label*="breadcrumb"] a, [class*="breadcrumb"] a, [class*="breadcrumb"] span'):
            text = clean_text(element.get_text(" ", strip=True))
            if text:
                breadcrumb_parts.append(text)

        if breadcrumb_parts:
            return " ".join(breadcrumb_parts)

        return None

    @staticmethod
    def extract_zone_from_listing(
        title: str | None,
        description: str | None,
        url: str | None,
        address: str | None = None,
    ) -> str | None:
        zone_aliases = [
            ("Alexandru cel Bun", ["alexandru-cel-bun", "alexandru cel bun"]),
            ("Tatarasi", ["tatarasi", "tătărași"]),
            ("Podu Ros", ["podu-ros", "podu ros", "podu roș"]),
            ("Nicolina", ["nicolina"]),
            ("Pacurari", ["pacurari", "păcurari"]),
            ("Centru", ["central", "centru", "ultracentral", "palas"]),
            ("CUG", ["cug"]),
            ("Moara de Vant", ["moara-de-vant", "moara de vant", "moara de vânt"]),
            ("Dacia", ["dacia"]),
            ("Tudor Vladimirescu", ["tudor-vladimirescu", "tudor vladimirescu"]),
            ("Mircea cel Batran", ["mircea-cel-batran", "mircea cel batran", "mircea cel bătrân"]),
            ("Bucium", ["bucium"]),
            ("Galata", ["galata"]),
            ("Frumoasa", ["frumoasa"]),
            ("Copou", ["copou"]),
        ]

        def find_zone(text: str | None) -> str | None:
            if not text:
                return None

            lowered = text.lower()

            for zone, aliases in zone_aliases:
                if any(alias in lowered for alias in aliases):
                    return zone

            return None

        # Highest confidence: actual address from the listing page.
        zone = find_zone(address)
        if zone:
            return zone

        # Medium confidence: title and URL.
        zone = find_zone(" ".join([title or "", url or ""]))
        if zone:
            return zone

        # Lowest confidence: description, because it can include unrelated page content.
        return find_zone(description)
        
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
        gallery_images = self.extract_gallery_images(soup, next_data)
        address = self.extract_listing_address(soup)
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
            possible_prices = recursive_find_values(next_data, {"price", "amount", "value"})
            possible_images = recursive_find_values(next_data, {"url", "src", "image"})

            if not title:
                title = self.pick_text(possible_titles)

            if not description:
                description = self.pick_text(possible_descriptions)

            if price is None:
                price = self.pick_price(possible_prices)

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
                "price_eur": parse_float(price) or self.extract_price_from_text(text_blob),
                "currency": self.extract_currency(text_blob, currency or "EUR"),
                "city": "Iasi",
                "zone": self.extract_zone_from_listing(
                    title,
                    self.extract_description_fallback(soup),
                    url,
                    address=address,
                ),
                "rooms": self.extract_rooms(text_blob),
                "surface_m2": self.extract_surface(text_blob),
                "floor": self.extract_floor(text_blob),
                "image_urls": gallery_images,
            }
        )

        return base

    def from_html_fallback(self, url: str, soup: BeautifulSoup) -> dict[str, Any]:
        text = soup.get_text(" ", strip=True)
        address = self.extract_listing_address(soup)
        title = None

        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)

        images = []
        for img in soup.select("img[src], img[srcset], img[data-src]"):
            for attr in ["src", "data-src", "srcset"]:
                value = img.get(attr)
                if not value:
                    continue

                if attr == "srcset":
                    parts = [p.strip().split(" ")[0] for p in value.split(",") if p.strip()]
                    images.extend(parts)
                else:
                    images.append(value)

        images = [x for x in images if self.is_imobiliare_listing_image(x)]

        return {
            "source": self.source_name,
            "source_listing_id": self.extract_source_id(url),
            "source_url": url,
            "title": clean_text(title),
            "description": self.extract_description_fallback(soup),
            "price_eur": self.extract_price_from_text(text),
            "currency": "EUR",
            "city": "Iasi",
            "zone": self.extract_zone_from_listing(
                title,
                self.extract_description_fallback(soup),
                url,
                address=address,
            ),
            "rooms": self.extract_rooms(text),
            "surface_m2": self.extract_surface(text),
            "floor": self.extract_floor(text),
            "image_urls": list(dict.fromkeys(images)),
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
        patterns = [
            r"/anunt/([^/?#]+)",
            r"-(\d+)\.html",
            r"/([^/]+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    @staticmethod
    def extract_price_from_text(text: str) -> float | None:
        if not text:
            return None

        normalized = text.replace("\xa0", " ")

        patterns = [
            r"(?:pret|preț|chirie|rent)[^\d]{0,20}(\d{2,6})\s*(?:€|eur|euro|ron|lei|leu)",
            r"(\d{2,6})\s*(?:€|eur|euro|ron|lei|leu)\s*(?:/ luna|/ lună|luna|lună)?",
            r"(?:€|eur|euro|ron|lei|leu)\s*(\d{2,6})",
        ]

        candidates = []

        for pattern in patterns:
            for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
                parsed = parse_float(match.group(1))
                if parsed and 50 <= parsed <= 50000:
                    candidates.append(parsed)

        if not candidates:
            return None

        return candidates[0]

    @staticmethod
    def extract_rooms(text: str) -> float | None:
        if re.search(r"garsonier[ăa]", text, flags=re.IGNORECASE):
            return 1

        patterns = [
            r"(\d+)\s*camere",
            r"(\d+)\s*camera",
            r"apartament\s+(\d+)\s*camere",
        ]

        for pattern in patterns:
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
            '[class*="description"]',
            '[id*="description"]',
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