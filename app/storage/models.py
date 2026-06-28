from datetime import datetime, date

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Float,
    Boolean,
    JSON,
    Text,
    UniqueConstraint,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RawListingSnapshot(Base):
    """
    Bronze/raw layer.
    One row per source listing per snapshot_date.
    This should be close to a 1:1 copy of what the scraper saw that day.
    """
    __tablename__ = "raw_listing_snapshots"

    id = Column(Integer, primary_key=True)

    snapshot_date = Column(Date, nullable=False, default=date.today)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    source = Column(String, nullable=False)
    source_listing_id = Column(String, nullable=True)
    source_url = Column(Text, nullable=False)

    title = Column(Text)
    description = Column(Text)

    price_eur = Column(Float)
    currency = Column(String, default="EUR")

    price_original = Column(Float)
    currency_original = Column(String)
    fx_rate_eur_ron = Column(Float)

    city = Column(String)
    zone = Column(String)
    address_text = Column(Text)

    latitude = Column(Float)
    longitude = Column(Float)

    rooms = Column(Float)
    surface_m2 = Column(Float)
    floor = Column(String)
    year_built = Column(Integer)

    agency_or_private = Column(String)
    seller_name = Column(String)

    image_urls = Column(JSON)
    local_image_paths = Column(JSON)

    raw_json = Column(JSON, nullable=False)
    content_hash = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "source",
            "source_url",
            name="uq_raw_snapshot_source_url",
        ),
    )


class CuratedListing(Base):
    """
    Silver/curated latest layer.
    Rebuilt from the latest raw snapshot.
    """
    __tablename__ = "curated_listings"

    id = Column(Integer, primary_key=True)

    snapshot_date = Column(Date, nullable=False)

    raw_snapshot_id = Column(Integer, ForeignKey("raw_listing_snapshots.id"), nullable=False)

    canonical_id = Column(String, nullable=False, index=True)
    duplicate_group_id = Column(String, index=True)

    source = Column(String, nullable=False)
    source_url = Column(Text, nullable=False)

    title = Column(Text)
    description = Column(Text)

    price_original = Column(Float)
    currency_original = Column(String)
    fx_rate_eur_ron = Column(Float)

    price_eur = Column(Float)
    price_eur_raw = Column(Float)
    price_eur_clean = Column(Float)
    price_per_m2 = Column(Float)

    city = Column(String)
    zone = Column(String)

    rooms = Column(Float)
    surface_m2 = Column(Float)

    image_count = Column(Integer, default=0)
    local_image_paths = Column(JSON)

    is_agency = Column(Boolean)
    is_private_owner = Column(Boolean)
    is_pet_friendly = Column(Boolean)

    upfront_rent_months = Column(Float)
    deposit_months = Column(Float)
    agency_commission_percent = Column(Float)
    agency_commission_months = Column(Float)

    has_upfront_cost_info = Column(Boolean, default=False)
    has_no_commission = Column(Boolean, default=False)
    has_parking = Column(Boolean, default=False)

    dq_price_suspicious = Column(Boolean, default=False)
    dq_missing_description = Column(Boolean, default=False)
    dq_missing_images = Column(Boolean, default=False)
    dq_is_category_page = Column(Boolean, default=False)

    listing_status = Column(String, default="active")

    first_seen_date = Column(Date)
    last_seen_date = Column(Date)

    local_price_percentile = Column(Float)
    anomaly_score = Column(Float)
    demand_score = Column(Float)
    description_score = Column(Float)
    image_score = Column(Float)
    worth_checking_score = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)


class ListingPriceHistory(Base):
    """
    Gold/staging analytics layer.
    One row per canonical listing per day.
    """
    __tablename__ = "listing_price_history"

    id = Column(Integer, primary_key=True)

    snapshot_date = Column(Date, nullable=False)
    canonical_id = Column(String, nullable=False, index=True)

    source = Column(String, nullable=False)
    source_url = Column(Text, nullable=False)

    city = Column(String)
    zone = Column(String)

    rooms = Column(Float)
    surface_m2 = Column(Float)

    price_eur = Column(Float)
    price_per_m2 = Column(Float)

    is_active_that_day = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "canonical_id",
            "source",
            "source_url",
            name="uq_price_history_daily_listing",
        ),
    )


class ListingLifecycle(Base):
    """
    Tracks disappearance/reappearance over time.
    """
    __tablename__ = "listing_lifecycle"

    id = Column(Integer, primary_key=True)

    canonical_id = Column(String, nullable=False, unique=True, index=True)

    first_seen_date = Column(Date)
    last_seen_date = Column(Date)
    disappeared_date = Column(Date)
    reappeared_date = Column(Date)

    days_seen = Column(Integer, default=0)
    days_missing = Column(Integer, default=0)

    current_status = Column(String, default="active")

    source_urls = Column(JSON)


class ListingImage(Base):
    """
    Downloaded/compressed images.
    """
    __tablename__ = "listing_images"

    id = Column(Integer, primary_key=True)

    snapshot_date = Column(Date, nullable=False)

    source = Column(String, nullable=False)
    source_url = Column(Text, nullable=False)
    image_url = Column(Text, nullable=False)

    local_path = Column(Text)
    width = Column(Integer)
    height = Column(Integer)

    phash = Column(String)
    file_size_bytes = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "source_url",
            "image_url",
            name="uq_listing_image_snapshot",
        ),
    )

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)

    run_type = Column(String, nullable=False)  # daily, manual, images, scrape
    status = Column(String, nullable=False)    # running, success, failed

    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)

    snapshot_date = Column(Date)
    message = Column(Text)

    raw_count = Column(Integer)
    curated_count = Column(Integer)
    top_count = Column(Integer)

class ScrapeQueue(Base):
    __tablename__ = "scrape_queue"

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False)

    source = Column(String, nullable=False)
    url = Column(Text, nullable=False)

    status = Column(String, default="pending")  # pending, running, success, failed
    attempts = Column(Integer, default=0)

    last_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("snapshot_date", "source", "url", name="uq_scrape_queue_daily_url"),
    )

class PreferenceProfile(Base):
    __tablename__ = "preference_profiles"

    id = Column(Integer, primary_key=True)

    name = Column(String, nullable=False, unique=True)
    config = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class IntermediateListingScore(Base):
    __tablename__ = "intermediate_listing_scores"

    id = Column(Integer, primary_key=True)

    snapshot_date = Column(Date, nullable=False)

    curated_listing_id = Column(Integer, ForeignKey("curated_listings.id"), nullable=False)
    canonical_id = Column(String, nullable=False, index=True)

    profile_name = Column(String, nullable=False, default="default")

    price_score = Column(Float)
    room_score = Column(Float)
    surface_score = Column(Float)
    location_score = Column(Float)
    feature_score = Column(Float)
    dq_score = Column(Float)
    trend_score = Column(Float)

    total_score = Column(Float)

    score_reasons = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "curated_listing_id",
            "profile_name",
            name="uq_intermediate_score_daily_listing_profile",
        ),
    )
