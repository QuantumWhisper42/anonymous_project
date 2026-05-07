from abc import abstractmethod
from dataclasses import KW_ONLY, dataclass, field
from async_lru import alru_cache
from typing import Literal, TypedDict

import aiolimiter
import anyio
from pydantic import TypeAdapter
from pydantic_ai import BinaryImage, ModelRetry, ToolReturn
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from lib.utils.image import (
    create_rate_limited_async_httpx_get,
    load_image_from_url,
)


class BaseImageSearchResult(TypedDict):
    title: str
    """The title of the search result."""
    image: str
    """The URL of the image from search result."""
    thumbnail: str
    """The URL of the thumbnail image from search result."""
    url: str
    """The URL of the search result. Points to the Web page that contains the image, not the image itself"""
    height: str
    """The height of the image from search result."""
    width: str
    """The width of the image from search result."""
    source: str
    """The source of the search result."""


image_search_ta = TypeAdapter(list[BaseImageSearchResult])


@dataclass
class BaseImageSearchTool:
    """Base Image search tool."""

    _: KW_ONLY

    limiter: aiolimiter.AsyncLimiter = field(
        default_factory=lambda: aiolimiter.AsyncLimiter(max_rate=5, time_period=60.0)
    )
    semaphore: anyio.Semaphore = field(default_factory=lambda: anyio.Semaphore(1))

    max_results: int | None
    """The maximum number of results. If None, returns results only from the first response."""

    safe_search: Literal["on", "moderate", "off"] = "moderate"

    license_image: str | None = None

    def __post_init__(self):
        self._load_image_httpx_get = create_rate_limited_async_httpx_get(
            user_agent=self._get_user_agent()
        )
        self._load_image_from_url = alru_cache(maxsize=32)(
            self._raw_load_image_from_url
        )

    @abstractmethod
    def _sync_search(self, query: str) -> list[BaseImageSearchResult]:
        raise NotImplementedError

    @abstractmethod
    async def _search(self, query: str) -> list[BaseImageSearchResult]:
        raise NotImplementedError

    def _get_user_agent(self) -> str | None:
        return None

    async def _raw_load_image_from_url(self, image_url: str) -> BinaryImage:
        """Loads an image from the given URL."""
        return await load_image_from_url(image_url, self._load_image_httpx_get)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=60),
        retry=retry_if_not_exception_type(ModelRetry),
    )
    async def __call__(self, query: str) -> ToolReturn:
        """Searches the internet for the given query and returns the results.

        Args:
            query: The query to search for.

        Returns:
            The search results.
        """
        async with self.limiter:
            async with self.semaphore:
                results = image_search_ta.validate_python(await self._search(query))

        return ToolReturn(
            return_value=[
                part
                for i, result in enumerate(results, 1)
                for part in (
                    f"Image {i} Title: {result['title']}",
                    f"Image {i} URL: {result['image']}",
                    await self._load_image_from_url(result["thumbnail"]),
                )
            ],
        )
