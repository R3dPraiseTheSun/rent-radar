import asyncio
import json

from app.pipeline.ingest import get_enabled_scrapers, load_yaml


async def main():
    locations = load_yaml("locations.yaml")["locations"]
    location = locations[0]

    city = location["city"]
    zones = location.get("zones", [])

    scrapers = get_enabled_scrapers()

    for scraper in scrapers:
        print("=" * 80)
        print(f"Testing scraper: {scraper.source_name}")

        urls = await scraper.search_listing_urls(city=city, zones=zones)
        print(f"Found {len(urls)} URLs")

        for url in urls[:3]:
            print("-" * 80)
            print(url)

            payload = await scraper.scrape_listing(url)

            preview = {
                "source": payload.get("source"),
                "source_listing_id": payload.get("source_listing_id"),
                "title": payload.get("title"),
                "price_eur": payload.get("price_eur"),
                "city": payload.get("city"),
                "zone": payload.get("zone"),
                "rooms": payload.get("rooms"),
                "surface_m2": payload.get("surface_m2"),
                "floor": payload.get("floor"),
                "image_count": len(payload.get("image_urls") or []),
                "source_url": payload.get("source_url"),
            }

            print(json.dumps(preview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())