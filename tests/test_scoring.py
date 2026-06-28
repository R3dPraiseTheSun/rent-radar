from datetime import date

from app.pipeline.scoring import score_one_listing, load_preferences
from app.storage.models import CuratedListing


def test_preferred_listing_scores_higher_than_bad_listing():
    prefs = load_preferences("default")

    good = CuratedListing(
        snapshot_date=date.today(),
        title="Apartament 2 camere pet friendly cu parcare",
        price_eur_clean=420,
        rooms=2,
        surface_m2=55,
        zone="Pacurari",
        is_pet_friendly=True,
        has_parking=True,
        has_no_commission=True,
        is_private_owner=True,
        dq_missing_images=False,
        dq_missing_description=False,
        dq_price_suspicious=False,
        dq_is_category_page=False,
    )

    bad = CuratedListing(
        snapshot_date=date.today(),
        title="Garsoniera scumpa fara poze",
        price_eur_clean=700,
        rooms=1,
        surface_m2=24,
        zone="Unknown",
        is_pet_friendly=False,
        has_parking=False,
        has_no_commission=False,
        is_private_owner=False,
        is_agency=True,
        dq_missing_images=True,
        dq_missing_description=True,
        dq_price_suspicious=False,
        dq_is_category_page=False,
    )

    class DummySession:
        def query(self, *args, **kwargs):
            class Q:
                def filter(self, *args, **kwargs): return self
                def order_by(self, *args, **kwargs): return self
                def first(self): return None
            return Q()

    session = DummySession()

    good_score = score_one_listing(session, good, prefs)["total_score"]
    bad_score = score_one_listing(session, bad, prefs)["total_score"]

    assert good_score > bad_score