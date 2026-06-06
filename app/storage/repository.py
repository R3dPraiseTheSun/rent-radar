import hashlib
import json
from datetime import date, datetime

from app.storage.models import RawListingSnapshot
from app.pipeline.fx import normalize_price_to_eur


def stable_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def insert_raw_snapshot(
    session,
    payload: dict,
    snapshot_date: date | None = None,
    eur_ron_rate: float | None = None,
) -> RawListingSnapshot:
    snapshot_date = snapshot_date or date.today()
    content_hash = stable_hash(payload)

    existing = (
        session.query(RawListingSnapshot)
        .filter(
            RawListingSnapshot.snapshot_date == snapshot_date,
            RawListingSnapshot.source == payload["source"],
            RawListingSnapshot.source_url == payload["source_url"],
        )
        .one_or_none()
    )

    price_original = payload.get("price_eur")
    currency_original = payload.get("currency", "EUR")
    price_eur = normalize_price_to_eur(
        price=price_original,
        currency=currency_original,
        eur_ron_rate=eur_ron_rate,
    )

    payload["price_original"] = price_original
    payload["currency_original"] = currency_original
    payload["price_eur_converted"] = price_eur
    payload["fx_rate_eur_ron"] = eur_ron_rate

    if existing:
        row = existing
    else:
        row = RawListingSnapshot(
            snapshot_date=snapshot_date,
            source=payload["source"],
            source_url=payload["source_url"],
        )
        session.add(row)

    row.scraped_at = datetime.utcnow()
    row.source_listing_id = payload.get("source_listing_id")
    row.title = payload.get("title")
    row.description = payload.get("description")
    row.price_original = price_original
    row.currency_original = currency_original
    row.fx_rate_eur_ron = eur_ron_rate
    row.price_eur = price_eur
    row.currency = "EUR"
    row.city = payload.get("city")
    row.zone = payload.get("zone")
    row.address_text = payload.get("address_text")
    row.latitude = payload.get("latitude")
    row.longitude = payload.get("longitude")
    row.rooms = payload.get("rooms")
    row.surface_m2 = payload.get("surface_m2")
    row.floor = payload.get("floor")
    row.year_built = payload.get("year_built")
    row.agency_or_private = payload.get("agency_or_private")
    row.seller_name = payload.get("seller_name")
    row.image_urls = payload.get("image_urls", [])
    row.local_image_paths = payload.get("local_image_paths", [])
    row.raw_json = payload
    row.content_hash = content_hash

    return row