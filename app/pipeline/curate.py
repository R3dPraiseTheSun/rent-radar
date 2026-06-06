import hashlib
from datetime import date, timedelta

from app.pipeline.description_features import extract_upfront_terms, description_score
from app.storage.models import (
    RawListingSnapshot,
    CuratedListing,
    ListingPriceHistory,
    ListingLifecycle,
)


def make_canonical_id(raw: RawListingSnapshot) -> str:
    source_id = raw.source_listing_id or ""

    if source_id:
        basis = f"{raw.source}|{source_id}"
    else:
        basis = "|".join(
            [
                raw.city or "",
                raw.zone or "",
                str(raw.rooms or ""),
                str(round(raw.surface_m2 or 0)),
                raw.title or "",
            ]
        )

    return hashlib.sha256(basis.lower().encode("utf-8")).hexdigest()[:16]


def clean_price(raw: RawListingSnapshot) -> tuple[float | None, bool]:
    price = raw.price_eur

    if price is None:
        return None, True

    suspicious = False

    if price < 100:
        suspicious = True

    if raw.rooms and raw.rooms >= 3 and raw.surface_m2 and raw.surface_m2 >= 60 and price < 300:
        suspicious = True

    if raw.surface_m2 and raw.surface_m2 >= 45 and price < 180:
        suspicious = True

    return price, suspicious


def is_category_page(raw: RawListingSnapshot) -> bool:
    if raw.source == "imobiliare_ro":
        return "/oferta/" not in raw.source_url

    if raw.source == "storia_ro":
        return "/ro/oferta/" not in raw.source_url

    return False


def rebuild_curated_latest(session, snapshot_date: date | None = None):
    snapshot_date = snapshot_date or date.today()

    session.query(CuratedListing).filter(
        CuratedListing.snapshot_date == snapshot_date
    ).delete()

    raw_rows = (
        session.query(RawListingSnapshot)
        .filter(RawListingSnapshot.snapshot_date == snapshot_date)
        .all()
    )

    for raw in raw_rows:
        category_page = is_category_page(raw)
        price_clean, price_suspicious = clean_price(raw)

        price_per_m2 = None
        if price_clean and raw.surface_m2 and raw.surface_m2 > 0:
            price_per_m2 = round(price_clean / raw.surface_m2, 2)

        features = extract_upfront_terms(
            title=raw.title,
            description=raw.description,
            seller_name=raw.seller_name,
        )

        desc_score = description_score(features)

        canonical_id = make_canonical_id(raw)

        curated = CuratedListing(
            snapshot_date=snapshot_date,
            raw_snapshot_id=raw.id,

            canonical_id=canonical_id,
            duplicate_group_id=canonical_id,

            source=raw.source,
            source_url=raw.source_url,

            title=raw.title,
            description=raw.description,

            price_eur_raw=raw.price_eur,
            price_eur_clean=price_clean,
            price_per_m2=price_per_m2,

            city=raw.city,
            zone=raw.zone,
            rooms=raw.rooms,
            surface_m2=raw.surface_m2,

            image_count=len(raw.image_urls or []),
            local_image_paths=raw.local_image_paths or [],

            is_agency=features["is_agency"],
            is_private_owner=features["is_private_owner"],
            is_pet_friendly=features["is_pet_friendly"],

            upfront_rent_months=features["upfront_rent_months"],
            deposit_months=features["deposit_months"],
            agency_commission_percent=features["agency_commission_percent"],
            agency_commission_months=features["agency_commission_months"],

            has_upfront_cost_info=features["has_upfront_cost_info"],
            has_no_commission=features["has_no_commission"],
            has_parking=features["has_parking"],

            dq_price_suspicious=price_suspicious,
            dq_missing_description=not bool(raw.description),
            dq_missing_images=len(raw.image_urls or []) == 0,
            dq_is_category_page=category_page,

            first_seen_date=snapshot_date,
            last_seen_date=snapshot_date,

            description_score=desc_score,
            image_score=min(len(raw.local_image_paths or []) / 6, 1.0),
        )

        session.add(curated)

    session.commit()


def update_price_history(session, snapshot_date: date | None = None):
    snapshot_date = snapshot_date or date.today()

    rows = (
        session.query(CuratedListing)
        .filter(CuratedListing.snapshot_date == snapshot_date)
        .filter(CuratedListing.dq_is_category_page == False)
        .all()
    )

    for row in rows:
        existing = (
            session.query(ListingPriceHistory)
            .filter(
                ListingPriceHistory.snapshot_date == snapshot_date,
                ListingPriceHistory.canonical_id == row.canonical_id,
                ListingPriceHistory.source == row.source,
                ListingPriceHistory.source_url == row.source_url,
            )
            .one_or_none()
        )

        if existing:
            hist = existing
        else:
            hist = ListingPriceHistory(
                snapshot_date=snapshot_date,
                canonical_id=row.canonical_id,
                source=row.source,
                source_url=row.source_url,
            )
            session.add(hist)

        hist.city = row.city
        hist.zone = row.zone
        hist.rooms = row.rooms
        hist.surface_m2 = row.surface_m2
        hist.price_eur = row.price_eur_clean
        hist.price_per_m2 = row.price_per_m2
        hist.is_active_that_day = True

    session.commit()


def update_lifecycle(session, snapshot_date: date | None = None):
    snapshot_date = snapshot_date or date.today()

    today_rows = (
        session.query(CuratedListing)
        .filter(CuratedListing.snapshot_date == snapshot_date)
        .filter(CuratedListing.dq_is_category_page == False)
        .all()
    )

    today_ids = {row.canonical_id for row in today_rows}

    for row in today_rows:
        lifecycle = (
            session.query(ListingLifecycle)
            .filter(ListingLifecycle.canonical_id == row.canonical_id)
            .one_or_none()
        )

        if not lifecycle:
            lifecycle = ListingLifecycle(
                canonical_id=row.canonical_id,
                first_seen_date=snapshot_date,
                source_urls=[],
            )
            session.add(lifecycle)

        if lifecycle.current_status == "disappeared":
            lifecycle.reappeared_date = snapshot_date
            lifecycle.current_status = "reappeared"
            lifecycle.days_missing = 0
        else:
            lifecycle.current_status = "active"

        lifecycle.last_seen_date = snapshot_date

        if lifecycle.first_seen_date and lifecycle.last_seen_date:
            lifecycle.days_seen = (
                lifecycle.last_seen_date - lifecycle.first_seen_date
            ).days + 1

        urls = set(lifecycle.source_urls or [])
        urls.add(row.source_url)
        lifecycle.source_urls = sorted(urls)

    existing_lifecycles = session.query(ListingLifecycle).all()

    for lifecycle in existing_lifecycles:
        if lifecycle.canonical_id not in today_ids:
            if lifecycle.last_seen_date and lifecycle.last_seen_date < snapshot_date:
                lifecycle.current_status = "disappeared"

                if not lifecycle.disappeared_date:
                    lifecycle.disappeared_date = snapshot_date

                lifecycle.days_missing = (
                    snapshot_date - lifecycle.last_seen_date
                ).days

    session.commit()