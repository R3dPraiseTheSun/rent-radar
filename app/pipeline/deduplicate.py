from datetime import date
from difflib import SequenceMatcher

from app.storage.models import CuratedListing


def text_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def pair_duplicate_score(a: CuratedListing, b: CuratedListing) -> float:
    score = 0.0

    if a.city and b.city and a.city.lower() == b.city.lower():
        score += 0.15

    if a.zone and b.zone and a.zone.lower() == b.zone.lower():
        score += 0.20

    if a.rooms and b.rooms and a.rooms == b.rooms:
        score += 0.15

    if a.surface_m2 and b.surface_m2 and abs(a.surface_m2 - b.surface_m2) <= 3:
        score += 0.15

    if a.price_eur_clean and b.price_eur_clean:
        diff = abs(a.price_eur_clean - b.price_eur_clean) / max(
            a.price_eur_clean,
            b.price_eur_clean,
        )
        if diff <= 0.05:
            score += 0.15

    if text_similarity(a.title, b.title) > 0.70:
        score += 0.10

    if a.source != b.source:
        score += 0.10

    return min(score, 1.0)


def run_deduplication(session, snapshot_date: date | None = None):
    snapshot_date = snapshot_date or date.today()

    listings = (
        session.query(CuratedListing)
        .filter(CuratedListing.snapshot_date == snapshot_date)
        .filter(CuratedListing.dq_is_category_page == False)
        .all()
    )

    for listing in listings:
        listing.duplicate_group_id = listing.canonical_id

    for i, a in enumerate(listings):
        for b in listings[i + 1:]:
            score = pair_duplicate_score(a, b)

            if score >= 0.75:
                group_id = min(a.duplicate_group_id, b.duplicate_group_id)
                a.duplicate_group_id = group_id
                b.duplicate_group_id = group_id

    session.commit()