from app.scrapers.base import BaseRentScraper


class MockScraper(BaseRentScraper):
    source_name = "mock"

    async def search_listing_urls(self, city: str, zones: list[str]) -> list[str]:
        return [
            "mock://listing/1",
            "mock://listing/2",
            "mock://listing/3",
            "mock://listing/duplicate-1",
        ]

    async def scrape_listing(self, url: str) -> dict:
        data = {
            "mock://listing/1": {
                "source": "mock",
                "source_listing_id": "1",
                "source_url": url,
                "title": "Apartament 2 camere Tineretului",
                "description": "Apartament luminos, aproape de metrou.",
                "price_eur": 430,
                "currency": "EUR",
                "city": "Bucuresti",
                "zone": "Tineretului",
                "rooms": 2,
                "surface_m2": 55,
                "floor": "3/8",
                "image_urls": ["https://example.com/a.jpg"],
                "raw_json": {},
            },
            "mock://listing/2": {
                "source": "mock",
                "source_listing_id": "2",
                "source_url": url,
                "title": "Garsoniera Dristor",
                "description": "Garsoniera renovata langa metrou Dristor.",
                "price_eur": 350,
                "currency": "EUR",
                "city": "Bucuresti",
                "zone": "Dristor",
                "rooms": 1,
                "surface_m2": 34,
                "floor": "6/10",
                "image_urls": ["https://example.com/b.jpg"],
                "raw_json": {},
            },
            "mock://listing/3": {
                "source": "mock",
                "source_listing_id": "3",
                "source_url": url,
                "title": "Apartament 3 camere Unirii",
                "description": "Apartament spatios in zona centrala.",
                "price_eur": 800,
                "currency": "EUR",
                "city": "Bucuresti",
                "zone": "Unirii",
                "rooms": 3,
                "surface_m2": 78,
                "floor": "2/7",
                "image_urls": ["https://example.com/c.jpg"],
                "raw_json": {},
            },
            "mock://listing/duplicate-1": {
                "source": "mock",
                "source_listing_id": "duplicate-1",
                "source_url": url,
                "title": "2 camere Tineretului aproape metrou",
                "description": "Apartament luminos, aproape de metrou.",
                "price_eur": 435,
                "currency": "EUR",
                "city": "Bucuresti",
                "zone": "Tineretului",
                "rooms": 2,
                "surface_m2": 55,
                "floor": "3/8",
                "image_urls": ["https://example.com/a-copy.jpg"],
                "raw_json": {},
            },
        }

        payload = data[url]
        payload["raw_json"] = dict(payload)
        return payload