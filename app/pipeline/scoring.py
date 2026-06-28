from datetime import date
from pathlib import Path

import yaml

from app.storage.models import CuratedListing, IntermediateListingScore, ListingPriceHistory


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def load_preferences(profile_name: str = "default") -> dict:
    path = CONFIG_DIR / "preferences.yaml"

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    profile = data.get(f"{profile_name}_profile") or data.get("default_profile")

    if not profile:
        raise RuntimeError("Missing default_profile in preferences.yaml")

    return profile


def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def score_price(row: CuratedListing, prefs: dict) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    price = row.price_eur_clean
    cfg = prefs["price"]

    if price is None:
        return -2.0, ["missing price"]

    target = cfg["target_max_eur"]
    hard_max = cfg["hard_max_eur"]

    if price <= target:
        score += cfg["under_target_bonus"]
        reasons.append(f"price under target €{target}")
    elif price <= hard_max:
        over = price - target
        penalty = (over / 100.0) * cfg["over_target_penalty_per_100_eur"]
        score -= penalty
        reasons.append(f"price over target by €{over:.0f}")
    else:
        score -= 2.0
        reasons.append(f"price over hard max €{hard_max}")

    return score, reasons


def score_rooms(row: CuratedListing, prefs: dict) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    rooms = row.rooms
    cfg = prefs["rooms"]

    if rooms is None:
        return -0.5, ["missing room count"]

    if int(rooms) in cfg["preferred"]:
        score += cfg["preferred_bonus"]
        reasons.append(f"{int(rooms)} rooms preferred")
    elif int(rooms) in cfg["acceptable"]:
        score += cfg["acceptable_bonus"]
        reasons.append(f"{int(rooms)} rooms acceptable")
    else:
        score -= cfg["bad_penalty"]
        reasons.append(f"{int(rooms)} rooms not preferred")

    return score, reasons


def score_surface(row: CuratedListing, prefs: dict) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    surface = row.surface_m2
    cfg = prefs["surface"]

    if surface is None:
        return -0.4, ["missing surface"]

    if surface < cfg["min_m2"]:
        score -= cfg["too_small_penalty"]
        reasons.append(f"surface below {cfg['min_m2']} m²")
    elif surface >= cfg["preferred_min_m2"]:
        score += cfg["preferred_bonus"]
        reasons.append(f"surface above {cfg['preferred_min_m2']} m²")

    return score, reasons


def score_features(row: CuratedListing, prefs: dict) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0
    cfg = prefs["features"]

    if row.has_parking:
        score += cfg["parking_bonus"]
        reasons.append("parking")

    if row.is_pet_friendly:
        score += cfg["pet_friendly_bonus"]
        reasons.append("pet friendly")

    if row.is_private_owner:
        score += cfg["private_owner_bonus"]
        reasons.append("private owner")

    if row.has_no_commission:
        score += cfg["no_commission_bonus"]
        reasons.append("no commission")

    if row.is_agency and not row.has_no_commission:
        score -= cfg["agency_penalty"]
        reasons.append("agency")

    if row.deposit_months and row.deposit_months >= 2:
        score -= cfg["high_deposit_penalty"]
        reasons.append("high deposit")

    if row.agency_commission_percent and row.agency_commission_percent >= 50:
        score -= cfg["high_commission_penalty"]
        reasons.append("high agency commission")

    if row.agency_commission_months and row.agency_commission_months >= 0.5:
        score -= cfg["high_commission_penalty"]
        reasons.append("agency commission months")

    return score, reasons


def score_location(row: CuratedListing, prefs: dict) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    cfg = prefs["location"]
    preferred = cfg.get("preferred_zones", [])

    if row.zone in preferred:
        score += cfg.get("preferred_zone_bonus", 0.0)
        reasons.append(f"preferred zone: {row.zone}")

    return score, reasons


def score_dq(row: CuratedListing, prefs: dict) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0
    cfg = prefs["data_quality"]

    if row.dq_missing_images:
        score -= cfg["missing_images_penalty"]
        reasons.append("missing images")

    if row.dq_missing_description:
        score -= cfg["missing_description_penalty"]
        reasons.append("missing description")

    if row.dq_price_suspicious:
        score -= cfg["suspicious_price_penalty"]
        reasons.append("suspicious price")

    if row.dq_is_category_page:
        score -= cfg["category_page_penalty"]
        reasons.append("category page")

    return score, reasons


def score_trend(session, row: CuratedListing) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    previous = (
        session.query(ListingPriceHistory)
        .filter(ListingPriceHistory.canonical_id == row.canonical_id)
        .filter(ListingPriceHistory.snapshot_date < row.snapshot_date)
        .order_by(ListingPriceHistory.snapshot_date.desc())
        .first()
    )

    if not previous or previous.price_eur is None or row.price_eur_clean is None:
        return 0.0, reasons

    if row.price_eur_clean < previous.price_eur:
        diff = previous.price_eur - row.price_eur_clean
        score += min(diff / 50.0, 1.0)
        reasons.append(f"price dropped €{diff:.0f}")

    return score, reasons


def score_one_listing(session, row: CuratedListing, prefs: dict) -> dict:
    price_score, price_reasons = score_price(row, prefs)
    room_score, room_reasons = score_rooms(row, prefs)
    surface_score, surface_reasons = score_surface(row, prefs)
    location_score, location_reasons = score_location(row, prefs)
    feature_score, feature_reasons = score_features(row, prefs)
    dq_score, dq_reasons = score_dq(row, prefs)
    trend_score, trend_reasons = score_trend(session, row)

    raw_total = (
        4.0
        + price_score
        + room_score
        + surface_score
        + location_score
        + feature_score
        + dq_score
        + trend_score
    )

    total = round(clamp(raw_total), 2)

    return {
        "price_score": round(price_score, 2),
        "room_score": round(room_score, 2),
        "surface_score": round(surface_score, 2),
        "location_score": round(location_score, 2),
        "feature_score": round(feature_score, 2),
        "dq_score": round(dq_score, 2),
        "trend_score": round(trend_score, 2),
        "total_score": total,
        "score_reasons": {
            "price": price_reasons,
            "rooms": room_reasons,
            "surface": surface_reasons,
            "location": location_reasons,
            "features": feature_reasons,
            "dq": dq_reasons,
            "trend": trend_reasons,
        },
    }


def rebuild_intermediate_scores(
    session,
    snapshot_date: date | None = None,
    profile_name: str = "default",
):
    snapshot_date = snapshot_date or date.today()
    prefs = load_preferences(profile_name)

    session.query(IntermediateListingScore).filter(
        IntermediateListingScore.snapshot_date == snapshot_date,
        IntermediateListingScore.profile_name == profile_name,
    ).delete()

    rows = (
        session.query(CuratedListing)
        .filter(CuratedListing.snapshot_date == snapshot_date)
        .filter(CuratedListing.dq_is_category_page == False)
        .all()
    )

    for row in rows:
        result = score_one_listing(session, row, prefs)

        score_row = IntermediateListingScore(
            snapshot_date=snapshot_date,
            curated_listing_id=row.id,
            canonical_id=row.canonical_id,
            profile_name=profile_name,
            price_score=result["price_score"],
            room_score=result["room_score"],
            surface_score=result["surface_score"],
            location_score=result["location_score"],
            feature_score=result["feature_score"],
            dq_score=result["dq_score"],
            trend_score=result["trend_score"],
            total_score=result["total_score"],
            score_reasons=result["score_reasons"],
        )

        row.worth_checking_score = result["total_score"]

        session.add(score_row)

    session.commit()