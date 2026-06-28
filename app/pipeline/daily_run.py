import os
import asyncio
from datetime import date

from app.pipeline.ingest import run_ingestion
from app.pipeline.curate import (
    rebuild_curated_latest,
    update_price_history,
    update_lifecycle,
)
from app.pipeline.deduplicate import run_deduplication
from app.pipeline.report import generate_daily_report
from app.storage.db import get_session, engine
from app.storage.models import Base, RawListingSnapshot, CuratedListing
from app.pipeline.images import process_latest_images

from app.pipeline.scoring import rebuild_intermediate_scores


async def main():
    snapshot_date = date.today()

    Base.metadata.create_all(bind=engine)

    print("[daily] starting raw snapshot ingestion")
    await run_ingestion(snapshot_date=snapshot_date)

    session = get_session()

    try:
        raw_count = (
            session.query(RawListingSnapshot)
            .filter(RawListingSnapshot.snapshot_date == snapshot_date)
            .count()
        )
        print(f"[daily] raw snapshots today: {raw_count}")

        image_enabled = os.getenv("IMAGE_DOWNLOAD_ENABLED", "true").lower() == "true"
        image_max_listings = int(os.getenv("IMAGE_MAX_LISTINGS", "60"))
        image_limit_per_listing = int(os.getenv("IMAGE_LIMIT_PER_LISTING", "4"))

        if not image_enabled:
        #     print("[daily] processing images")
        #     await process_latest_images(
        #         session=session,
        #         snapshot_date=snapshot_date,
        #         max_listings=image_max_listings,
        #         limit_per_listing=image_limit_per_listing,
        #     )
        # else:
            print("[daily] image processing disabled")

        print("[daily] rebuilding curated latest")
        rebuild_curated_latest(session, snapshot_date=snapshot_date)

        curated_count = (
            session.query(CuratedListing)
            .filter(CuratedListing.snapshot_date == snapshot_date)
            .count()
        )
        print(f"[daily] curated listings today: {curated_count}")

        print("[daily] deduplicating curated layer")
        run_deduplication(session, snapshot_date=snapshot_date)

        print("[daily] updating price history")
        update_price_history(session, snapshot_date=snapshot_date)

        print("[daily] updating lifecycle")
        update_lifecycle(session, snapshot_date=snapshot_date)

        print("[daily] rebuilding intermediate scores")
        rebuild_intermediate_scores(
            session=session,
            snapshot_date=snapshot_date,
            profile_name="default",
        )

        if image_enabled:
            print("[daily] processing images for top recommendations")
            await process_images_for_top_curated(
                session=session,
                snapshot_date=snapshot_date,
                max_listings=image_max_listings,
                limit_per_listing=image_limit_per_listing,
            )

            print("[daily] rebuilding curated after images")
            rebuild_curated_latest(session, snapshot_date=snapshot_date)

            print("[daily] rebuilding scores after images")
            rebuild_intermediate_scores(session, snapshot_date=snapshot_date, profile_name="default")

        print("[daily] generating report")
        result = generate_daily_report(session, snapshot_date=snapshot_date)

        print(result)

    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())