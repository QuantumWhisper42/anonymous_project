from dataclasses import dataclass

import anyio
import anyio.to_thread
from mwclient import Site
from pydantic_ai.tools import Tool

from .base_image_search import BaseImageSearchResult, BaseImageSearchTool

__all__ = ("wikimedia_commons_image_search_tool",)

import os

DEFAULT_WIKIMEDIA_COMMONS_URL = "commons.wikimedia.org"
DEFAULT_USER_AGENT = os.environ.get(
    "WIKIMEDIA_COMMONS_USER_AGENT",
    "AnonymousProject/0.0 (anonymous_project@example.com)",
)


from typing import Any


def get_commons_metadata(
    file_names: list[str], user_agent: str = DEFAULT_USER_AGENT
) -> dict[str, dict[str, str]]:
    site = Site("commons.wikimedia.org", clients_useragent=user_agent)
    results: dict[str, dict[str, str]] = {}

    batch_size = 50
    for i in range(0, len(file_names), batch_size):
        batch = file_names[i : i + batch_size]

        res = site.api(
            "query",
            prop="imageinfo",
            titles="|".join(batch),
            iiprop="extmetadata|url",
            iiextmetadatafilter="LicenseShortName|LicenseUrl|Artist|UsageTerms",
            iiextmetadatalanguage="en",
        )

        pages: dict[str, Any] = res.get("query", {}).get("pages", {})

        for page_data in pages.values():
            title = page_data.get("title", "")
            if not title:
                continue

            info_dict = {
                "title": title,
                "author": "Unknown",
                "source": "",
                "license": "Unknown",
                "license_url": "",
            }

            imageinfo = page_data.get("imageinfo", [{}])[0]
            metadata = imageinfo.get("extmetadata", {})

            if imageinfo:
                info_dict["Source"] = imageinfo.get("descriptionurl", "")

            if metadata:
                info_dict["Author"] = metadata.get("Artist", {}).get("value", "Unknown")
                info_dict["License"] = metadata.get("LicenseShortName", {}).get(
                    "value", "Unknown"
                )
                info_dict["LicenseUrl"] = metadata.get("LicenseUrl", {}).get(
                    "value", ""
                )

            if not info_dict["LicenseUrl"] and (
                "PUBLIC DOMAIN" in info_dict["License"].upper()
                or "PD" in info_dict["License"].upper()
            ):
                info_dict["LicenseUrl"] = (
                    "https://creativecommons.org/publicdomain/mark/1.0/"
                )

            results[title] = info_dict

    return results


@dataclass
class WikimediaCommonsImageSearchTool(BaseImageSearchTool):
    """The Wikimedia Commons search tool."""

    site: Site
    """The Wikimedia Commons search client."""

    user_agent: str | None
    """The User-Agent to call Wikimedia API."""

    def _sync_search(self, search_query: str) -> list[BaseImageSearchResult]:
        try:
            params = {
                "action": "query",
                "format": "json",
                "uselang": "en",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap|drawing -fileres:0{' haslicense:' + self.license_image if self.license_image else ''} {search_query}",
                "gsrlimit": self.max_results or 10,
                "gsroffset": 0,
                "gsrinfo": "totalhits|suggestion",
                "gsrprop": "size|wordcount|timestamp|snippet",
                "prop": "info|imageinfo|entityterms",
                "inprop": "url",
                "gsrnamespace": 6,
                "iiprop": "url|size|mime",
                "iiurlheight": "500",
                "wbetterms": "label",
            }
            res = self.site.get(**params)
            pages = res.get("query", {}).get("pages", {}).values()

            output: list[BaseImageSearchResult] = []
            for page in pages:
                if not isinstance(page, dict):
                    continue

                img_info_list = page.get("imageinfo", [])
                if not (img_info_list and isinstance(img_info_list, list)):
                    continue

                info = img_info_list[0]

                output.append(
                    {
                        "title": page["title"].replace("File:", ""),
                        "image": info["url"],
                        "thumbnail": info["thumburl"],
                        "url": page["fullurl"],
                        "width": str(info["width"]),
                        "height": str(info["height"]),
                        "source": "WikiMedia Commons",
                    }
                )
                if len(output) >= (self.max_results or 0):
                    break
            return output
        except Exception as e:
            print(e)
            return []

    async def _search(self, query: str) -> list[BaseImageSearchResult]:
        """Searches Wikimedia Commons for the given query and returns the results.

        Args:
            query: The query to search for.

        Returns:
            The search results.
        """

        return await anyio.to_thread.run_sync(self._sync_search, query)

    def _get_user_agent(self) -> str | None:
        return self.user_agent


def wikimedia_commons_image_search_tool(
    site_url: str = DEFAULT_WIKIMEDIA_COMMONS_URL,
    user_agent: str = DEFAULT_USER_AGENT,
    max_results: int = 3,
    license_image: str | None = None,
):
    """Creates a Wikimedia Commons search tool.

    Args:
        site_url: The Wikimedia Commons url.
        user_agent: The User-Agent to call Wikimedia API. SHOULD confirm to https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
        max_results: The maximum number of results. If None, returns results only from the first response.
        license_image: The license to filter image search.
    """
    site = Site(site_url, clients_useragent=user_agent)

    return Tool(
        WikimediaCommonsImageSearchTool(
            site=site,
            user_agent=user_agent,
            max_results=max_results,
            license_image=license_image,
        ).__call__,
        name="wikimedia_image_search",
        description=f"Searches Wikimedia Commons for the given query and returns the results. max results: {max_results}",
    )
