from abc import ABC, abstractmethod


class BaseRentScraper(ABC):
    source_name: str

    @abstractmethod
    async def search_listing_urls(self, city: str, zones: list[str]) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def scrape_listing(self, url: str) -> dict:
        raise NotImplementedError