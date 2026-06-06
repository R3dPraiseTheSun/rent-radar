import asyncio
import os
import yaml
import traceback
from pathlib import Path

from app.scrapers.mock import MockScraper
from app.storage.db import get_session, engine, SessionLocal
from app.storage.models import Base
from app.storage.repository import insert_raw_snapshot
from app.pipeline.fx import get_eur_ron_rate


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_enabled_scrapers():
    sites = load_yaml("sites.yaml")["sites"]

    scrapers = []

    if sites.get("mock", {}).get("enabled"):
        from app.scrapers.mock import MockScraper
        scrapers.append(MockScraper())

    if sites.get("storia_ro", {}).get("enabled"):
        from app.scrapers.storia import StoriaScraper

        cfg = sites["storia_ro"]
        scrapers.append(
            StoriaScraper(
                base_url=cfg.get("base_url", "https://www.storia.ro"),
                city_slug=cfg.get("city_slug", "iasi"),
                max_pages=cfg.get("max_pages_per_run", 3),
                rate_limit_seconds=cfg.get("rate_limit_seconds", 4),
            )
        )

    if sites.get("imobiliare_ro", {}).get("enabled"):
        from app.scrapers.imobiliare import ImobiliareScraper

        cfg = sites["imobiliare_ro"]
        scrapers.append(
            ImobiliareScraper(
                base_url=cfg.get("base_url", "https://www.imobiliare.ro"),
                city_slug=cfg.get("city_slug", "iasi"),
                max_pages=cfg.get("max_pages_per_run", 3),
                rate_limit_seconds=cfg.get("rate_limit_seconds", 4),
            )
        )

    return scrapers

def suspicious_price(payload: dict) -> bool:
    price = payload.get("price_eur")
    rooms = payload.get("rooms")
    surface = payload.get("surface_m2")

    if price is None:
        return True

    if price < 120:
        return True

    if rooms and rooms >= 3 and surface and surface >= 60 and price < 300:
        return True

    if surface and surface >= 45 and price < 200:
        return True

    return False


async def scrape_and_save_url(
    semaphore,
    scraper,
    url,
    session_factory,
    snapshot_date,
    eur_ron_rate,
):
    async with semaphore:
        session = session_factory()

        try:
            print(f"[ingest] scraping url={url}")

            payload = await scraper.scrape_listing(url)

            if suspicious_price(payload):
                print(
                    "[ingest] suspicious price, saving but flagging "
                    f"source={payload.get('source')} "
                    f"title={payload.get('title')} "
                    f"price={payload.get('price_eur')} "
                    f"rooms={payload.get('rooms')} "
                    f"surface={payload.get('surface_m2')} "
                    f"url={url}"
                )
                payload["price_suspicious"] = True
            else:
                payload["price_suspicious"] = False

            if not payload:
                print(f"[ingest] skipping empty payload: {url}")
                continue

            if not payload.get("source_url"):
                print(f"[ingest] skipping malformed payload: {url}")
                continue

            if payload.get("source") == "storia_ro":
                if "/hpr/" in payload.get("source_url", ""):
                    print(f"[ingest] skipping non-canonical Storia URL: {url}")
                    continue

            if payload.get("source") == "imobiliare_ro":
                if "/oferta/" not in payload.get("source_url", ""):
                    print(f"[ingest] skipping non-offer Imobiliare URL: {url}")
                    continue

            if not payload.get("title") and not payload.get("price_eur"):
                print(
                    "[ingest] skipping low-quality payload "
                    f"title={payload.get('title')} "
                    f"price={payload.get('price_eur')} "
                    f"url={url}"
                )
                continue

            insert_raw_snapshot(
                session,
                payload,
                snapshot_date=snapshot_date,
                eur_ron_rate=eur_ron_rate,
            )
            session.commit()
            saved_count += 1

            print(
                "[ingest] saved "
                f"source={payload.get('source')} "
                f"title={payload.get('title')} "
                f"price={payload.get('price_eur')} "
                f"rooms={payload.get('rooms')} "
                f"surface={payload.get('surface_m2')} "
                f"url={url}"
            )

        except Exception as exc:
            session.rollback()
            print(f"[ingest] failed url={url}, error={repr(exc)}")
            return False

        finally:
            session.close()


async def run_ingestion(snapshot_date=None):
    Base.metadata.create_all(bind=engine)

    eur_ron_rate = await get_eur_ron_rate(snapshot_date=snapshot_date)
    print(f"[ingest] EUR/RON rate={eur_ron_rate}")
    
    locations = load_yaml("locations.yaml")["locations"]
    scrapers = get_enabled_scrapers()

    print(f"[ingest] locations={locations}")
    print(f"[ingest] enabled_scrapers={[s.source_name for s in scrapers]}")

    if not scrapers:
        print("[ingest] ERROR: no scrapers enabled")
        return

    session = get_session()
    saved_count = 0

    try:
        for location in locations:
            city = location["city"]
            zones = location.get("zones", [])

            for scraper in scrapers:
                print(f"[ingest] source={scraper.source_name}, city={city}, zones={zones}")

                urls = await scraper.search_listing_urls(city=city, zones=zones)
                print(f"[ingest] source={scraper.source_name}, found_urls={len(urls)}")

                concurrency = int(os.getenv("SCRAPER_CONCURRENCY", "4"))
                semaphore = asyncio.Semaphore(concurrency)

                tasks = [
                    scrape_and_save_url(
                        semaphore=semaphore,
                        scraper=scraper,
                        url=url,
                        session_factory=SessionLocal,
                        snapshot_date=snapshot_date,
                        eur_ron_rate=eur_ron_rate,
                    )
                    for url in urls
                ]

                results = await asyncio.gather(*tasks)

                saved_count += sum(1 for ok in results if ok)

        print(f"[ingest] done, saved_count={saved_count}")

    finally:
        session.close()


def main():
    asyncio.run(run_ingestion())


if __name__ == "__main__":
    main()