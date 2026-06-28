from bs4 import BeautifulSoup

from app.scrapers.utils import is_probable_listing_image


def test_probable_listing_image_filters_logos():
    assert is_probable_listing_image("https://example.com/photos/apartment-1.jpg")
    assert not is_probable_listing_image("https://example.com/static/logo.svg")
    assert not is_probable_listing_image("https://example.com/favicon.ico")