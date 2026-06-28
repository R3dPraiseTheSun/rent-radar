from datetime import date
from pathlib import Path

import pandas as pd

from app.storage.models import CuratedListing, IntermediateListingScore

EXPORT_DIR = Path("/data/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    df["local_median_price_per_m2"] = (
        df.groupby(["city", "zone", "rooms"])["price_per_m2"]
        .transform("median")
    )

    df["city_room_median_price_per_m2"] = (
        df.groupby(["city", "rooms"])["price_per_m2"]
        .transform("median")
    )

    df["local_median_price_per_m2"] = df["local_median_price_per_m2"].fillna(
        df["city_room_median_price_per_m2"]
    )

    df["cheapness_ratio"] = (
        df["local_median_price_per_m2"] - df["price_per_m2"]
    ) / df["local_median_price_per_m2"]

    df["cheapness_score"] = (
        df["cheapness_ratio"]
        .fillna(0)
        .clip(lower=0, upper=0.35) / 0.35
    )

    df["dq_penalty"] = 0.0
    df.loc[df["dq_price_suspicious"] == True, "dq_penalty"] += 2.0
    df.loc[df["dq_missing_images"] == True, "dq_penalty"] += 0.5
    df.loc[df["dq_missing_description"] == True, "dq_penalty"] += 0.4
    df.loc[df["dq_is_category_page"] == True, "dq_penalty"] += 5.0

    df["pet_bonus"] = df["is_pet_friendly"].fillna(False).astype(float) * 0.6
    df["private_bonus"] = df["is_private_owner"].fillna(False).astype(float) * 0.5
    df["no_commission_bonus"] = df["has_no_commission"].fillna(False).astype(float) * 0.5
    df["parking_bonus"] = df["has_parking"].fillna(False).astype(float) * 0.25

    df["description_score"] = df["description_score"].fillna(0)
    df["image_score"] = df["image_score"].fillna(0)

    df["worth_checking_score"] = (
        df["cheapness_score"] * 4.0
        + df["description_score"] * 0.8
        + df["image_score"] * 1.0
        + df["pet_bonus"]
        + df["private_bonus"]
        + df["no_commission_bonus"]
        + df["parking_bonus"]
        - df["dq_penalty"]
    )

    df["worth_checking_score"] = (
        df["worth_checking_score"]
        .clip(lower=0, upper=10)
        .round(2)
    )

    return df


def latest_snapshot_date(session):
    result = (
        session.query(CuratedListing.snapshot_date)
        .order_by(CuratedListing.snapshot_date.desc())
        .first()
    )
    return result[0] if result else date.today()


def generate_daily_report(session, snapshot_date=None, profile_name: str = "default"):
    snapshot_date = snapshot_date or latest_snapshot_date(session)

    rows = (
        session.query(CuratedListing, IntermediateListingScore)
        .join(
            IntermediateListingScore,
            IntermediateListingScore.curated_listing_id == CuratedListing.id,
        )
        .filter(CuratedListing.snapshot_date == snapshot_date)
        .filter(IntermediateListingScore.profile_name == profile_name)
        .all()
    )

    data = []

    for row, score in rows:
        data.append(
            {
                "id": row.id,
                "snapshot_date": row.snapshot_date,
                "duplicate_group_id": row.duplicate_group_id,
                "canonical_id": row.canonical_id,
                "source": row.source,
                "source_url": row.source_url,
                "title": row.title,
                "description": row.description,
                "city": row.city,
                "zone": row.zone,
                "rooms": row.rooms,
                "surface_m2": row.surface_m2,
                "price_eur_raw": row.price_eur_raw,
                "price_eur_clean": row.price_eur_clean,
                "price_per_m2": row.price_per_m2,
                "image_count": row.image_count,
                "local_image_paths": row.local_image_paths,
                "is_agency": row.is_agency,
                "is_private_owner": row.is_private_owner,
                "is_pet_friendly": row.is_pet_friendly,
                "has_no_commission": row.has_no_commission,
                "has_parking": row.has_parking,
                "upfront_rent_months": row.upfront_rent_months,
                "deposit_months": row.deposit_months,
                "agency_commission_percent": row.agency_commission_percent,
                "agency_commission_months": row.agency_commission_months,
                "dq_price_suspicious": row.dq_price_suspicious,
                "dq_missing_description": row.dq_missing_description,
                "dq_missing_images": row.dq_missing_images,
                "dq_is_category_page": row.dq_is_category_page,
                "price_score": score.price_score,
                "room_score": score.room_score,
                "surface_score": score.surface_score,
                "location_score": score.location_score,
                "feature_score": score.feature_score,
                "dq_score": score.dq_score,
                "trend_score": score.trend_score,
                "worth_checking_score": score.total_score,
                "score_reasons": score.score_reasons,
            }
        )

    df = pd.DataFrame(data)

    if df.empty:
        daily_db = df
        top = df
    else:
        daily_db = df.copy()

        top = df[
            (df["dq_is_category_page"] == False)
            & (df["dq_price_suspicious"] == False)
        ].copy()

        top = top.sort_values("worth_checking_score", ascending=False).head(50)

    date_str = snapshot_date.isoformat()

    daily_csv = EXPORT_DIR / f"daily_full_db_{date_str}.csv"
    top_csv = EXPORT_DIR / f"daily_top_picks_{date_str}.csv"
    top_json = EXPORT_DIR / f"top_picks_{date_str}.json"

    daily_db.to_csv(daily_csv, index=False)
    top.to_csv(top_csv, index=False)
    top.to_json(top_json, orient="records", force_ascii=False, indent=2)

    return {
        "snapshot_date": date_str,
        "daily_csv": str(daily_csv),
        "top_csv": str(top_csv),
        "top_json": str(top_json),
        "daily_count": len(daily_db),
        "top_count": len(top),
    }