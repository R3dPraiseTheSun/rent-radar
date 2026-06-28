import os
import pytest

from app.scrapers.storia import StoriaScraper
from app.scrapers.imobiliare import ImobiliareScraper


pytestmark = pytest.mark.asyncio


RUN_LIVE = os.getenv("RUN_LIVE_SCRAPER_TESTS", "false").lower() == "true"


@pytest.mark.skipif(not RUN_LIVE, reason="Live scraper smoke tests disabled")
async def test_storia_scraper_smoke():
    scraper = StoriaScraper(
        city_slug="iasi",
        max_pages=1,
        rate_limit_seconds=1,
    )

    urls = await scraper.search_listing_urls(city="Iasi", zones=[])

    assert len(urls) >= 1

    payloads = []

    for url in urls[:5]:
        payload = await scraper.scrape_listing(url)
        if payload and payload.get("title") and payload.get("price_eur"):
            payloads.append(payload)

    assert 1 <= len(payloads) <= 5

    for payload in payloads:
        assert payload["source"] == "storia_ro"
        assert payload["source_url"]
        assert payload["title"]
        assert payload["price_eur"]


@pytest.mark.skipif(not RUN_LIVE, reason="Live scraper smoke tests disabled")
async def test_imobiliare_scraper_smoke():
    scraper = ImobiliareScraper(
        city_slug="iasi",
        max_pages=1,
        rate_limit_seconds=1,
    )

    urls = await scraper.search_listing_urls(city="Iasi", zones=[])

    urls = [url for url in urls if "/oferta/" in url]

    assert len(urls) >= 1

    payloads = []

    for url in urls[:5]:
        payload = await scraper.scrape_listing(url)
        if payload and payload.get("title") and payload.get("price_eur"):
            payloads.append(payload)

    assert 1 <= len(payloads) <= 5

    for payload in payloads:
        assert payload["source"] == "imobiliare_ro"
        assert "/oferta/" in payload["source_url"]
        assert payload["title"]
        assert payload["price_eur"]