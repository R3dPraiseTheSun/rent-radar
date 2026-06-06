import asyncio
import os
import hashlib
from datetime import date
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
import imagehash

from app.storage.models import ListingImage, RawListingSnapshot


IMAGE_DIR = Path("/data/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def image_key(source_url: str, image_url: str) -> str:
    raw = f"{source_url}|{image_url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


async def download_and_compress_image(
    image_url: str,
    source_url: str,
    source: str,
    snapshot_date: date,
    max_width: int = 900,
    quality: int = 72,
) -> dict | None:
    try:
        headers = {
            "User-Agent": "RentRadarBot/0.1 personal research project",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(image_url)

        if response.status_code >= 400:
            print(f"[images] HTTP {response.status_code}, skipping image={image_url}")
            return None

        content_type = response.headers.get("content-type", "").lower()
        if "image" not in content_type:
            print(f"[images] non-image content-type={content_type}, url={image_url}")
            return None

        img = Image.open(BytesIO(response.content)).convert("RGB")

        original_width, original_height = img.size

        if original_width > max_width:
            ratio = max_width / original_width
            new_size = (max_width, int(original_height * ratio))
            img = img.resize(new_size)

        key = image_key(source_url, image_url)

        date_dir = IMAGE_DIR / snapshot_date.isoformat()
        date_dir.mkdir(parents=True, exist_ok=True)

        local_path = date_dir / f"{key}.webp"

        img.save(local_path, format="WEBP", quality=quality, method=6)

        phash = str(imagehash.phash(img))
        size_bytes = local_path.stat().st_size

        return {
            "image_url": image_url,
            "source_url": source_url,
            "source": source,
            "snapshot_date": snapshot_date,
            "local_path": str(local_path),
            "width": img.size[0],
            "height": img.size[1],
            "phash": phash,
            "file_size_bytes": size_bytes,
        }

    except Exception as exc:
        print(f"[images] failed image={image_url}, error={repr(exc)}")
        return None


async def process_listing_images(
    session,
    raw_snapshot: RawListingSnapshot,
    limit_per_listing: int = 6,
) -> list[str]:
    image_urls = raw_snapshot.image_urls or []
    image_urls = image_urls[:limit_per_listing]

    local_paths = []

    for image_url in image_urls:
        existing = (
            session.query(ListingImage)
            .filter(
                ListingImage.snapshot_date == raw_snapshot.snapshot_date,
                ListingImage.source_url == raw_snapshot.source_url,
                ListingImage.image_url == image_url,
            )
            .one_or_none()
        )

        if existing:
            if existing.local_path:
                local_paths.append(existing.local_path)
            continue

        result = await download_and_compress_image(
            image_url=image_url,
            source_url=raw_snapshot.source_url,
            source=raw_snapshot.source,
            snapshot_date=raw_snapshot.snapshot_date,
        )

        if not result:
            continue

        row = ListingImage(**result)
        session.add(row)
        local_paths.append(result["local_path"])

    raw_snapshot.local_image_paths = local_paths
    session.commit()

    return local_paths


async def process_latest_images(
    session,
    snapshot_date: date,
    max_listings: int = 60,
    limit_per_listing: int = 4,
):
    rows = (
        session.query(RawListingSnapshot)
        .filter(RawListingSnapshot.snapshot_date == snapshot_date)
        .filter(RawListingSnapshot.image_urls != None)
        .limit(max_listings)
        .all()
    )

    image_concurrency = int(os.getenv("IMAGE_CONCURRENCY", "4"))
    semaphore = asyncio.Semaphore(image_concurrency)

    async def one(row_id: int):
        from app.storage.db import SessionLocal

        async with semaphore:
            local_session = SessionLocal()
            try:
                row = local_session.query(RawListingSnapshot).filter(
                    RawListingSnapshot.id == row_id
                ).one_or_none()

                if not row:
                    return 0

                paths = await process_listing_images(
                    session=local_session,
                    raw_snapshot=row,
                    limit_per_listing=limit_per_listing,
                )

                print(
                    f"[images] listing_id={row.id}, "
                    f"downloaded_or_existing={len(paths)}, "
                    f"title={row.title}"
                )

                return len(paths)

            finally:
                local_session.close()

    results = await asyncio.gather(*[one(row.id) for row in rows])
    processed = sum(1 for count in results if count > 0)

    print(f"[images] processed listings with images: {processed}/{len(rows)}")