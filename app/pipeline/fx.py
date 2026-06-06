import json
from datetime import date
from pathlib import Path

import httpx


FX_CACHE = Path("/data/fx_rates.json")
FX_CACHE.parent.mkdir(parents=True, exist_ok=True)


def load_cache() -> dict:
    if not FX_CACHE.exists():
        return {}

    try:
        return json.loads(FX_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache: dict):
    FX_CACHE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def get_eur_ron_rate(snapshot_date: date | None = None) -> float:
    snapshot_date = snapshot_date or date.today()
    key = snapshot_date.isoformat()

    cache = load_cache()

    if key in cache and "EUR_RON" in cache[key]:
        return float(cache[key]["EUR_RON"])

    url = "https://api.frankfurter.dev/v1/latest?from=EUR&to=RON"

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    payload = response.json()
    rate = float(payload["rates"]["RON"])

    cache.setdefault(key, {})
    cache[key]["EUR_RON"] = rate
    save_cache(cache)

    return rate


def normalize_price_to_eur(
    price: float | None,
    currency: str | None,
    eur_ron_rate: float | None,
) -> float | None:
    if price is None:
        return None

    currency = (currency or "EUR").upper().strip()

    if currency in ["EUR", "EURO", "€"]:
        return float(price)

    if currency in ["RON", "LEI", "LEU"]:
        if not eur_ron_rate:
            return None
        return round(float(price) / eur_ron_rate, 2)

    return float(price)