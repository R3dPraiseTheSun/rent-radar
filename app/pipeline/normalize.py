import hashlib
from datetime import date

from app.storage.models import RawListing, CuratedListing


def make_canonical_id(raw: RawListing) -> str:
    basis = "|".join(
        [
            raw.city or "",
            raw.zone or "",
            str(raw.rooms or ""),
            str(round(raw.surface_m2 or 0)),
            str(round(raw.price_eur or 0)),
            raw.title or "",
        ]
    )
    return hashlib.sha256(basis.lower().encode("utf-8")).hexdigest()[:16]


def normalize_raw_to_curated(session):
    session.query(CuratedListing).delete()

    raw_listings = session.query(RawListing).filter(RawListing.is_active == True).all()

    today = date.today()

    for raw in raw_listings:
        price_per_m2 = None
        if raw.price_eur and raw.surface_m2 and raw.surface_m2 > 0:
            price_per_m2 = round(raw.price_eur / raw.surface_m2, 2)

        curated = CuratedListing(
            raw_listing_id=raw.id,
            canonical_id=make_canonical_id(raw),
            source=raw.source,
            source_url=raw.source_url,
            title=raw.title,
            price_eur=raw.price_eur,
            price_per_m2=price_per_m2,
            city=raw.city,
            zone=raw.zone,
            rooms=raw.rooms,
            surface_m2=raw.surface_m2,
            image_count=len(raw.image_urls or []),
            first_seen_at=raw.first_seen_at,
            last_seen_at=raw.last_seen_at,
            is_new_today=raw.first_seen_at.date() == today,
        )
        session.add(curated)

    session.commit()